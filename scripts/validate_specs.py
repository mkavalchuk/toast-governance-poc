"""Check that each file in specs/ is a valid OpenAPI document and print its version.

Toast publishes its specs as Swagger 2.0 (the predecessor of OpenAPI 3), so both
`openapi:` and `swagger:` top-level keys are accepted.
"""

import sys
from pathlib import Path

import yaml

SPECS_DIR = Path(__file__).resolve().parent.parent / "specs"


def main() -> int:
    failed = False
    for path in sorted(SPECS_DIR.glob("*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(spec, dict) or not ("openapi" in spec or "swagger" in spec):
            print(f"{path.name}: no top-level 'openapi' or 'swagger' key")
            failed = True
            continue
        info = spec.get("info", {})
        print(
            f"{path.name}: format={'openapi ' + str(spec['openapi']) if 'openapi' in spec else 'swagger ' + str(spec['swagger'])} "
            f"title={info.get('title')!r} version={info.get('version')!r} "
            f"paths={len(spec.get('paths', {}))}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
