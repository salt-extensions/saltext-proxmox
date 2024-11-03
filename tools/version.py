"""
Very simple heuristic to generate the next version number
based on the current changelog news fragments.

This looks for the most recent version by parsing the
CHANGELOG.md file and increments a specific part,
depending on the fragment types present and their contents.

Major bumps are caused by:
  * files named `.removed.md`
  * files named `.breaking.md`
  * files containing `BREAKING:`

Minor bumps are caused by:
  * files named `.added.md`

Otherwise, only the patch version is bumped.
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(".").resolve()
CHANGELOG_DIR = PROJECT_ROOT / "changelog"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"


class Version:
    def __init__(self, version):
        match = re.search(r"v?(?P<release>[0-9]+(?:\.[0-9]+)*)", version)
        if not match:
            raise ValueError(f"Invalid version: '{version}'")
        self.release = tuple(int(i) for i in match.group("release").split("."))

    @property
    def major(self):
        return self._ret(0)

    @property
    def minor(self):
        return self._ret(1)

    @property
    def patch(self):
        return self._ret(2)

    def __str__(self):
        return ".".join(str(i) for i in self.release)

    def _ret(self, cnt):
        try:
            return self.release[cnt]
        except IndexError:
            return 0


def last_release():
    for line in CHANGELOG_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            return Version(line.split(" ")[1])
    return Version("0.0.0")


def get_next_version(last):
    major = minor = False

    for fragment in CHANGELOG_DIR.glob("[!.]*"):
        name = fragment.name.lower()
        if ".added" in name:
            minor = True
        elif ".breaking" in name or ".removed" in name:
            major = True
            break
        if "breaking:" in fragment.read_text(encoding="utf-8").lower():
            major = True
            break
    if major:
        return Version(f"{last.major + 1}.0.0")
    if minor:
        return Version(f"{last.major}.{last.minor + 1}.0")
    return Version(f"{last.major}.{last.minor}.{last.patch + 1}")


if __name__ == "__main__":
    try:
        if sys.argv[1] == "next":
            print(get_next_version(last_release()))
            raise SystemExit(0)
    except IndexError:
        pass
    print(last_release())
