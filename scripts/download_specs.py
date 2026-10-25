"""Download Toast's 17 published API specifications into specs/.

The download links come from each API's overview page on doc.toasttab.com
("Download OpenAPI specification"). Specs are not committed to this repo.
"""

import sys
from pathlib import Path

import requests

from build_toast_metadata import APIS

BASE = "https://doc.toasttab.com/toast-api-specifications/"
SPECS = Path(__file__).resolve().parent.parent / "specs"


def main() -> int:
    SPECS.mkdir(exist_ok=True)
    for file in APIS:
        r = requests.get(BASE + file, timeout=60)
        r.raise_for_status()
        (SPECS / file).write_bytes(r.content)
        print(f"{file:<48} {len(r.content):>8,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
