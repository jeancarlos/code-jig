import re
import sys

VERSION = r"v?(\d+)(?:\.(\d+))?(?:[.+-][0-9A-Za-z.+-]*)?"
BUMP = re.compile(rf"chore\(deps\): bump (\S+) from {VERSION} to {VERSION}(?: in /\S*)?")


def same_major(title: str) -> bool:
    m = BUMP.fullmatch(title)
    if not m:
        return False
    _, old_major, old_minor, new_major, new_minor = m.groups()
    return old_major == new_major and (old_major != "0" or old_minor == new_minor)


if __name__ == "__main__":
    sys.exit(0 if same_major(sys.argv[1]) else 1)
