import json
import re
import sqlite3
import sys
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, offset INTEGER NOT NULL, size INTEGER NOT NULL, thread_id TEXT, model TEXT, turn_id TEXT, line INTEGER NOT NULL, last_total INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS threads (id TEXT PRIMARY KEY, parent_id TEXT, kind TEXT NOT NULL, started TEXT, cwd TEXT);
CREATE TABLE IF NOT EXISTS usage (thread_id TEXT NOT NULL, key TEXT NOT NULL, turn_id TEXT, ts TEXT, model TEXT, input INTEGER, cached INTEGER, output INTEGER, reasoning INTEGER, PRIMARY KEY (thread_id, key));
CREATE TABLE IF NOT EXISTS calls (thread_id TEXT NOT NULL, call_id TEXT NOT NULL, turn_id TEXT, ts TEXT, cmd TEXT, escalated INTEGER NOT NULL, PRIMARY KEY (thread_id, call_id));
CREATE TABLE IF NOT EXISTS compactions (thread_id TEXT NOT NULL, line INTEGER NOT NULL, ts TEXT, PRIMARY KEY (thread_id, line));
CREATE TABLE IF NOT EXISTS quarantine (path TEXT NOT NULL, line INTEGER NOT NULL, reason TEXT, PRIMARY KEY (path, line));
CREATE TABLE IF NOT EXISTS call_results (thread_id TEXT NOT NULL, call_id TEXT NOT NULL, exit_code INTEGER, skill TEXT, PRIMARY KEY (thread_id, call_id));
CREATE TABLE IF NOT EXISTS skill_reads (thread_id TEXT NOT NULL, call_id TEXT NOT NULL, skill TEXT NOT NULL, PRIMARY KEY (thread_id, call_id, skill));
CREATE TABLE IF NOT EXISTS guardian (thread_id TEXT NOT NULL, line INTEGER NOT NULL, ts TEXT, outcome TEXT NOT NULL, PRIMARY KEY (thread_id, line));
CREATE VIEW IF NOT EXISTS turn_usage AS
  SELECT u.*, COALESCE(t.kind, 'main') AS kind, t.parent_id AS parent_id
  FROM usage u LEFT JOIN threads t ON t.id = u.thread_id
  WHERE u.key NOT LIKE 'tc:%' OR u.thread_id NOT IN (SELECT thread_id FROM usage WHERE key NOT LIKE 'tc:%');
DROP VIEW IF EXISTS call_view;
CREATE VIEW call_view AS
  SELECT c.*, r.exit_code AS exit_code
  FROM calls c LEFT JOIN call_results r ON r.thread_id = c.thread_id AND r.call_id = c.call_id;
"""
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
CMD = re.compile(r'\bcmd:\s*"((?:[^"\\]|\\.)*)"')
EXIT = re.compile(r'"exit_code"\s*:\s*(-?\d+)|Exit code:\s*(-?\d+)|exited with code\s+(-?\d+)')
SKILL = re.compile(r"skills[/\\]+([A-Za-z0-9_.-]+)[/\\]+SKILL\.md")
OUTPUTS = ("function_call_output", "custom_tool_call_output")


def db_path(home: Path) -> Path:
    return home / "codex-harness" / "usage.sqlite3"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.executescript(SCHEMA)
    return con


def rollout_files(home: Path) -> list[Path]:
    return sorted([*home.glob("sessions/**/rollout-*.jsonl"), *home.glob("archived_sessions/rollout-*.jsonl")])


def kind_of(meta: dict) -> str:
    src = meta.get("source")
    if meta.get("thread_source") == "guardian_review" or (isinstance(src, dict) and src.get("subagent") == {"other": "guardian"}):
        return "guardian"
    if isinstance(src, dict) and "subagent" in src:
        return "subagent"
    return "main"


def _s(v) -> str | None:
    return v if isinstance(v, str) else None


def _usage(u) -> tuple[int, ...] | None:
    if not isinstance(u, dict) or not all(isinstance(u.get(k), int) and not isinstance(u.get(k), bool) for k in USAGE_KEYS):
        return None
    return tuple(u[k] for k in USAGE_KEYS)


def tool_call(payload: dict) -> tuple[str, str, bool] | None:
    kind, call_id = payload.get("type"), payload.get("call_id")
    if not isinstance(call_id, str):
        return None
    if kind == "custom_tool_call":
        text = payload.get("input")
        m = CMD.search(text) if isinstance(text, str) else None
        if not m:
            return None
        return call_id, _decode(m.group(1)), "require_escalated" in text
    if kind == "function_call":
        try:
            args = json.loads(payload.get("arguments") or "{}")
        except (TypeError, ValueError):
            return None
        if not isinstance(args, dict):
            return None
        cmd = args.get("cmd", args.get("command"))
        if isinstance(cmd, list):
            cmd = " ".join(str(c) for c in cmd)
        if not isinstance(cmd, str):
            return None
        return call_id, cmd, args.get("sandbox_permissions") == "require_escalated"
    return None


def _decode(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except ValueError:
        return raw


def cell_commands(payload: dict) -> list[str]:
    text = payload.get("input") if payload.get("type") == "custom_tool_call" else None
    return [_decode(m) for m in CMD.findall(text)] if isinstance(text, str) else []


def _output_text(payload: dict) -> str:
    out = payload.get("output")
    if isinstance(out, list):
        return "\n".join(o["text"] for o in out if isinstance(o, dict) and isinstance(o.get("text"), str))
    return out if isinstance(out, str) else ""


def exit_code(payload: dict) -> int | None:
    text = _output_text(payload)
    try:
        meta = json.loads(text).get("metadata")
    except (ValueError, AttributeError):
        meta = None
    if isinstance(meta, dict) and isinstance(meta.get("exit_code"), int):
        return meta["exit_code"]
    m = EXIT.search(text)
    return int(next(g for g in m.groups() if g is not None)) if m else None


def skills_of(cmd: str) -> list[str]:
    return list(dict.fromkeys(SKILL.findall(cmd)))


def guardian_outcome(payload: dict) -> str | None:
    try:
        msg = json.loads(payload.get("last_agent_message") or "")
    except (TypeError, ValueError):
        return None
    return msg["outcome"] if isinstance(msg, dict) and isinstance(msg.get("outcome"), str) else None


def _response_item(con: sqlite3.Connection, thread: str, turn: str | None, ts: str | None, p: dict) -> None:
    call = tool_call(p)
    if call:
        rows = [(call[0], call[1], int(call[2]))]
        rows += [(f"{call[0]}#{i}", cmd, 0) for i, cmd in enumerate(cell_commands(p)[1:], start=2)]
        for call_id, cmd, escalated in rows:
            con.execute("INSERT OR IGNORE INTO calls (thread_id, call_id, turn_id, ts, cmd, escalated) VALUES (?,?,?,?,?,?)",
                        (thread, call_id, turn, ts, cmd, escalated))
            for skill in skills_of(cmd):
                con.execute("INSERT OR IGNORE INTO skill_reads VALUES (?,?,?)", (thread, call_id, skill))
    elif p.get("type") in OUTPUTS and isinstance(p.get("call_id"), str):
        code = exit_code(p)
        if code is not None:
            con.execute("INSERT INTO call_results (thread_id, call_id, exit_code) SELECT ?, ?, ? "
                        "WHERE EXISTS (SELECT 1 FROM calls WHERE thread_id = ? AND call_id = ?) "
                        "AND NOT EXISTS (SELECT 1 FROM calls WHERE thread_id = ? AND call_id = ? || '#2') "
                        "ON CONFLICT(thread_id, call_id) DO UPDATE SET exit_code = excluded.exit_code WHERE call_results.exit_code IS NULL",
                        (thread, p["call_id"], code, thread, p["call_id"], thread, p["call_id"]))


def _scan_file(con: sqlite3.Connection, path: Path) -> tuple[int, int]:
    size = path.stat().st_size
    row = con.execute("SELECT offset, thread_id, model, turn_id, line, last_total FROM files WHERE path=?", (str(path),)).fetchone()
    offset, thread, model, turn, line, last_total = row or (0, None, None, None, 0, -1)
    if size < offset:
        offset, thread, model, turn, line, last_total = 0, None, None, None, 0, -1
    if size == offset:
        return 0, 0
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n") + 1
    count = bad = 0
    for raw in data[:end].split(b"\n")[:-1]:
        line += 1
        count += 1

        def quarantine(reason: str) -> None:
            nonlocal bad
            bad += 1
            con.execute("INSERT OR IGNORE INTO quarantine VALUES (?,?,?)", (str(path), line, reason))

        try:
            try:
                o = json.loads(raw)
            except ValueError:
                quarantine("not JSON")
                continue
            p = o.get("payload") if isinstance(o, dict) else None
            if not isinstance(p, dict):
                quarantine("no payload")
                continue
            t, ts = o.get("type"), o.get("timestamp")
            if t == "session_meta":
                if thread is None and isinstance(p.get("id"), str):
                    thread = p["id"]
                    con.execute("INSERT OR REPLACE INTO threads VALUES (?,?,?,?,?)",
                                (thread, _s(p.get("parent_thread_id")), kind_of(p), _s(p.get("timestamp")) or _s(ts), _s(p.get("cwd"))))
            elif thread is None:
                quarantine("before session_meta")
            elif t == "turn_context":
                model = _s(p.get("model")) or model
                turn = _s(p.get("turn_id")) or turn
            elif t == "token_usage_record":
                u = _usage(p.get("usage"))
                if u is None or not isinstance(p.get("response_id"), str):
                    quarantine("token_usage_record shape")
                    continue
                con.execute("INSERT OR IGNORE INTO usage VALUES (?,?,?,?,?,?,?,?,?)",
                            (thread, p["response_id"], _s(p.get("turn_id")) or turn, _s(ts), model, *u))
            elif t == "event_msg" and p.get("type") == "token_count":
                info = p.get("info")
                if info is None:
                    continue
                total = (info.get("total_token_usage") or {}).get("total_tokens") if isinstance(info, dict) else None
                u = _usage(info.get("last_token_usage")) if isinstance(info, dict) else None
                if u is None or not isinstance(total, int):
                    quarantine("token_count shape")
                    continue
                if total == last_total:
                    continue
                last_total = total
                con.execute("INSERT OR IGNORE INTO usage VALUES (?,?,?,?,?,?,?,?,?)",
                            (thread, f"tc:{line}", turn, _s(ts), model, *u))
            elif t == "compacted":
                con.execute("INSERT OR IGNORE INTO compactions VALUES (?,?,?)", (thread, line, _s(ts)))
            elif t == "response_item":
                _response_item(con, thread, turn, _s(ts), p)
            elif t == "event_msg" and p.get("type") == "task_complete":
                outcome = guardian_outcome(p)
                if outcome and con.execute("SELECT 1 FROM threads WHERE id=? AND kind='guardian'", (thread,)).fetchone():
                    con.execute("INSERT OR IGNORE INTO guardian VALUES (?,?,?,?)", (thread, line, _s(ts), outcome))
        except Exception as e:
            quarantine(type(e).__name__)
    con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?)",
                (str(path), offset + end, size, thread, model, turn, line, last_total))
    return count, bad


def scan(con: sqlite3.Connection, home: Path, rescan: bool = False) -> dict[str, int]:
    if rescan:
        with con:
            for table in ("files", "threads", "usage", "calls", "compactions", "quarantine", "guardian", "call_results", "skill_reads"):
                con.execute(f"DELETE FROM {table}")
    summary = {"files": 0, "lines": 0, "quarantined": 0}
    for path in rollout_files(home):
        with con:
            lines, bad = _scan_file(con, path)
        summary["files"] += 1
        summary["lines"] += lines
        summary["quarantined"] += bad
    return summary


def cli(args) -> int:
    from harness import paths
    try:
        home = paths.codex_home(args.codex_home)
        con = connect(db_path(home))
        try:
            summary = scan(con, home, rescan=args.rescan)
        finally:
            con.close()
        print(f"harness collect: {summary['files']} files, {summary['lines']} new lines, {summary['quarantined']} quarantined", file=sys.stderr)
    except Exception as e:
        print(f"harness collect: {type(e).__name__}: {e}", file=sys.stderr)
    print("{}")
    return 0
