import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from codejig import collect

TWO_WORD = {"git", "npm", "pnpm", "yarn", "cargo", "go", "uv", "dotnet", "docker", "kubectl", "gh"}
POLL = ("sleep", "wait")


def prefix(cmd: str) -> str:
    words = [w for w in cmd.split() if not ("=" in w and not w.startswith("-") and w.split("=", 1)[0].isidentifier())]
    if not words:
        return ""
    first = words[0].replace("\\", "/").rsplit("/", 1)[-1]
    if first in TWO_WORD and len(words) > 1 and not words[1].startswith("-"):
        return f"{first} {words[1]}"
    return first


def summary(con: sqlite3.Connection, since: str, top: int = 10, long_turns: int = 300) -> dict:
    rows = con.execute("SELECT thread_id, kind, parent_id, turn_id, model, input, cached, output FROM turn_usage WHERE ts >= ?", (since,)).fetchall()
    calls = con.execute("SELECT thread_id, cmd, escalated FROM calls WHERE ts >= ?", (since,)).fetchall()
    comps = Counter(t for (t,) in con.execute("SELECT thread_id FROM compactions WHERE ts >= ?", (since,)))
    by_kind: dict[str, int] = defaultdict(int)
    models: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sessions: dict[str, dict] = {}
    reviews = set()
    for thread, kind, parent, turn, model, inp, cached, out in rows:
        by_kind[kind] += inp
        models[model or "(unknown)"][0] += inp
        models[model or "(unknown)"][1] += out
        owner = parent if kind != "main" and parent else thread
        s = sessions.setdefault(owner, {"id": owner, "turns": 0, "input": 0, "cached": 0, "guardian_input": 0,
                                        "subagent_input": 0, "compactions": comps.get(owner, 0), "polling": 0})
        if kind == "guardian":
            s["guardian_input"] += inp
            reviews.add((thread, turn))
        elif kind == "subagent":
            s["subagent_input"] += inp
        else:
            s["input"] += inp
            s["cached"] += cached
            s["turns"] += 1
    for thread, cmd, _ in calls:
        if thread in sessions and cmd.lstrip().split(" ", 1)[0] in POLL:
            sessions[thread]["polling"] += 1
    total = sum(by_kind.values())
    guardian = by_kind.get("guardian", 0)
    ranked = sorted(sessions.values(), key=lambda s: s["input"] + s["guardian_input"] + s["subagent_input"], reverse=True)
    return {
        "input": total,
        "cached": sum(r[6] for r in rows),
        "output": sum(r[7] for r in rows),
        "by_kind": dict(by_kind),
        "guardian_share": guardian / total if total else 0.0,
        "reviews": len(reviews),
        "input_per_review": guardian / len(reviews) if reviews else 0,
        "escalations": Counter(prefix(c) for _, c, e in calls if e).most_common(),
        "sessions": ranked[:top],
        "over_long": sum(1 for s in sessions.values() if s["turns"] > long_turns),
        "models": sorted(((m, v[0], v[1]) for m, v in models.items()), key=lambda r: r[1], reverse=True),
        "quarantined": con.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0],
    }


def _safe(text: str) -> str:
    return "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in text)


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "-"


def render(s: dict, floor: float) -> list[str]:
    out = [
        f"Input {s['input']:,}  cached {_pct(s['cached'], s['input'])}  output {s['output']:,}",
        f"Guardian share of input: {100 * s['guardian_share']:.1f}%  reviews {s['reviews']}  input per review {s['input_per_review']:,.0f}",
        f"Sessions over 300 model requests: {s['over_long']}",
        "",
        "Top sessions (own input, cache hit, model requests, compactions, polling calls, Guardian input, subagent input):",
    ]
    for x in s["sessions"]:
        hit = 100 * x["cached"] / x["input"] if x["input"] else 100.0
        flag = "  LOW" if x["input"] and hit < floor else ""
        out.append(f"  {_safe(x['id'])}  {x['input']:,}  {hit:.1f}%{flag}  {x['turns']}  {x['compactions']}  {x['polling']}  {x['guardian_input']:,}  {x['subagent_input']:,}")
    out += ["", "Escalations sent to Guardian, by command:"]
    out += [f"  {_safe(p) or '(empty)'}  {n}" for p, n in s["escalations"]] or ["  none"]
    out += ["", "By model (input, output):"]
    out += [f"  {_safe(m)}  {i:,}  {o:,}" for m, i, o in s["models"]] or ["  none"]
    if s["quarantined"]:
        out += ["", f"warning: {s['quarantined']} rollout lines quarantined; see the quarantine table"]
    return out


def cli(args) -> int:
    path = collect.db_path()
    if not path.is_file():
        print(f"code-jig: {path} not found; run code-jig collect", file=sys.stderr)
        return 2
    con = collect.connect(path)
    try:
        since = (datetime.now(UTC) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for line in render(summary(con, since, args.top), args.cache_floor):
            print(line)
    finally:
        con.close()
    return 0
