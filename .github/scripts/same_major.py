import re
import sys

BUMP = re.compile(r"^chore\(deps\): bump (\S+) from v?(\d+)(?:\.\S*)? to v?(\d+)(?:\.\S*)?$")


def same_major(title: str) -> bool:
    m = BUMP.fullmatch(title)
    return bool(m) and m.group(2) == m.group(3)


if __name__ == "__main__":
    sys.exit(0 if same_major(sys.argv[1]) else 1)
