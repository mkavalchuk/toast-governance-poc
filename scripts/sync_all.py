"""Rebuild and re-sync the whole Toast catalog in dependency order.

Run after changing the specs or any classification, tagging or glossary rule.
Each step is safe to rerun on its own.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

STEPS = [
    ("build_toast_metadata.py", ["--push"]),   # tables, columns, tiers, privacy tags
    ("business_glossary.py", ["--push"]),      # KPI and filing terms, owner groups
    ("platform_glossary.py", ["--push"]),      # Toast platform glossary and API concepts
    ("link_terms.py", ["--push"]),             # operational data terms on columns
    ("lineage_model.py", []),                  # illustrative KPI model and dashboard
    ("assign_domain.py", []),                  # schemas into the Toast domain
    ("subdomains_owners.py", []),              # tables into subdomains, owners and stewards
    ("term_domains.py", []),                   # glossary terms into subdomains
    ("assign_data_product.py", []),
    ("catalog_guide.py", []),                  # data product description and reading guide
    ("structured_properties.py", []),          # certification and classification properties
    ("compliance_forms.py", []),
    ("policies.py", []),
    ("metadata_tests.py", []),
    ("monitor.py", []),
]


def main() -> int:
    only = set(sys.argv[1:])
    for script, args in STEPS:
        if only and script not in only:
            continue
        if not (HERE / script).exists():
            print(f"-- skip {script} (not present)")
            continue
        print(f"== {script}", flush=True)
        result = subprocess.run([sys.executable, str(HERE / script), *args], cwd=HERE.parent)
        if result.returncode:
            print(f"!! {script} failed with exit code {result.returncode}")
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
