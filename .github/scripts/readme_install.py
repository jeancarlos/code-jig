import re
import sys
from pathlib import Path

START, END = "<!-- install:start -->", "<!-- install:end -->"
TAG = re.compile(r"v\d+\.\d+\.\d+")
RELEASES = "https://github.com/jeancarlos/code-jig/releases"


def render(tag: str) -> str:
    if not TAG.fullmatch(tag):
        raise ValueError(f"not a release tag: {tag!r}")
    url = f"{RELEASES}/download/{tag}/bootstrap.py"
    return f"""{START}
Latest release: **{tag}**. Everything downloads from GitHub. Copy a block as it is; it runs without edits.

Linux and macOS:

```sh
curl -fsSL {url} | python3 -I -
```

Windows (PowerShell):

```powershell
irm {url} -OutFile bootstrap.py
py -3 -I bootstrap.py
```

To use your own overlay instead of the default `~/code-jig-overlay`, add `--overlay` and its folder or git URL at the end of the `python3`/`py` line, for example `--overlay ~/my-overlay`.

A piped script cannot check itself. To read what you run, download only `bootstrap.py`, read it, then run it:

```sh
curl -fsSL -o bootstrap.py {url}
python3 -I bootstrap.py
```

`bootstrap.py` has no checksum of its own; reading it is the check. The bootstrap downloads the zip itself and checks it against the release's `SHA256SUMS`. That catches a corrupted download, but not a compromised GitHub release. Releases before v0.11.0 have no zip.

**No one-liner allowed?** On a machine that blocks the download or PATH edits, download `code-jig.zip`, `SHA256SUMS` and `bootstrap.py` from the [{tag} release page]({RELEASES}/tag/{tag}) into one folder and run `py -3 -I bootstrap.py --zip code-jig.zip` there (`python3 -I` on Linux and macOS). The launcher does not need to be on PATH: the generated `AGENTS.md` tells agents its full path.
{END}"""


def update(text: str, tag: str) -> str:
    start, end = text.find(START), text.find(END)
    if start < 0 or end < start:
        raise ValueError(f"README has no {START} ... {END} block")
    return text[:start] + render(tag) + text[end + len(END):]


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("README.md")
    old = path.read_text(encoding="utf-8")
    new = update(old, argv[0])
    if new != old:
        path.write_bytes(new.encode("utf-8"))
    print(f"README install block {'updated' if new != old else 'already'} at {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
