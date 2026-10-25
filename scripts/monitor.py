"""Governance monitors for the Toast API catalog, reported to DataHub as custom assertions.

  Schema drift               every table   live spec from doc.toasttab.com vs. columns in DataHub
  Classification coverage    every table   every column carries exactly one Classification term
  Restricted data masked     Restricted    no real sample value is shown for a Restricted column

Each run downloads Toast's published specs again, rebuilds the expected columns with
the same logic as build_toast_metadata.py, and reports SUCCESS or FAILURE with details.
Results appear on each table's Quality tab and in Observe > Data Health. Run it on a
schedule (daily is plenty) to catch Toast API releases.
"""

import tempfile
import time
from pathlib import Path

import requests

import build_toast_metadata as builder
from dh import gql

SPEC_BASE = "https://doc.toasttab.com/toast-api-specifications/"
CLASS_PREFIX = "urn:li:glossaryTerm:Classification."
MASK = "masked (Restricted)"
PLATFORM = {"name": "Toast Governance Monitor"}

SCHEMA_Q = """query($u: String!) { dataset(urn: $u) {
  schemaMetadata { fields { fieldPath glossaryTerms { terms { term { urn } } } } }
  datasetProfiles(limit: 1) { fieldProfiles { fieldPath sampleValues } } } }"""


def expected_columns() -> dict:
    """dataset urn -> (set of field paths, api version) from Toast's live specs."""
    tmp = Path(tempfile.mkdtemp(prefix="toast-specs-"))
    for file in builder.APIS:
        r = requests.get(SPEC_BASE + file, timeout=60)
        r.raise_for_status()
        (tmp / file).write_bytes(r.content)
    builder.SPECS = tmp
    mcps, _ = builder.build()
    out, versions = {}, {}
    for m in mcps:
        name = type(m.aspect).__name__
        if name == "SchemaMetadataClass":
            out[m.entityUrn] = {f.fieldPath for f in m.aspect.fields}
        elif name == "DatasetPropertiesClass":
            versions[m.entityUrn] = m.aspect.customProperties.get("api_version", "")
    return {u: (cols, versions.get(u, "")) for u, cols in out.items()}


def assertion(aid, dataset, kind, description, logic, field_paths=None):
    urn = f"urn:li:assertion:{aid}"
    gql("mutation($u: String!, $i: UpsertCustomAssertionInput!) { upsertCustomAssertion(urn: $u, input: $i) { urn } }", {
        "u": urn, "i": {"entityUrn": dataset, "type": kind, "description": description, "platform": PLATFORM,
                        "logic": logic, "externalUrl": "https://doc.toasttab.com/openapi/",
                        **({"fieldPaths": field_paths} if field_paths else {})}})
    return urn


def report(urn, ok, props):
    gql("mutation($u: String!, $r: AssertionResultInput!) { reportAssertionResult(urn: $u, result: $r) }", {
        "u": urn, "r": {"timestampMillis": int(time.time() * 1000), "type": "SUCCESS" if ok else "FAILURE",
                        "properties": [{"key": k, "value": str(v)} for k, v in props.items()]}})


def short(items, n=10):
    items = sorted(items)
    return ", ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "") if items else "none"


def main() -> int:
    expected = expected_columns()
    tally = {"Schema drift": [0, 0], "Classification coverage": [0, 0], "Restricted data masked": [0, 0]}

    for ds, (want, version) in sorted(expected.items()):
        name = ds.split(",")[1]
        data = gql(SCHEMA_Q, {"u": ds})["dataset"]
        if not data or not data["schemaMetadata"]:
            continue
        fields = data["schemaMetadata"]["fields"]
        have = {f["fieldPath"] for f in fields}

        # 1. Schema drift against Toast's live published spec.
        added, removed = want - have, have - want
        urn = assertion(f"toast-schema-drift.{name}", ds, "Schema drift",
                        "Columns in DataHub match Toast's currently published API spec.",
                        f"Download {SPEC_BASE}... and rebuild expected columns; compare field paths.")
        ok = not added and not removed
        report(urn, ok, {"spec_version": version, "new_in_spec": short(added), "missing_from_spec": short(removed),
                         "columns": len(have)})
        tally["Schema drift"][0 if ok else 1] += 1

        # 2. Classification coverage.
        tiers = {f["fieldPath"]: [t["term"]["urn"] for t in (f.get("glossaryTerms") or {}).get("terms", [])
                                  if t["term"]["urn"].startswith(CLASS_PREFIX)] for f in fields}
        unclassified = [p for p, t in tiers.items() if len(t) != 1]
        urn = assertion(f"toast-classification-coverage.{name}", ds, "Classification coverage",
                        "Every column has exactly one Classification term (Public, Internal, Confidential or Restricted).",
                        "For each schema field, count glossary terms under the Classification node; expect exactly 1.")
        ok = not unclassified
        report(urn, ok, {"columns": len(fields), "unclassified": len(unclassified), "examples": short(unclassified, 5)})
        tally["Classification coverage"][0 if ok else 1] += 1

        # 3. Restricted columns never expose a real sample value.
        restricted = [p for p, t in tiers.items() if t == [CLASS_PREFIX + "Restricted"]]
        if restricted:
            samples = {p["fieldPath"]: p.get("sampleValues") or [] for p in
                       ((data.get("datasetProfiles") or [{}])[0].get("fieldProfiles") or [])}
            leaks = [p for p in restricted if any(MASK not in v for v in samples.get(p, []))]
            urn = assertion(f"toast-restricted-masked.{name}", ds, "Restricted data masked",
                            "Sample values for Restricted columns are masked; no card, contact, credential or pay values are exposed.",
                            "For each Restricted column, every sample value must contain the mask marker.",
                            field_paths=restricted[:50])
            ok = not leaks
            report(urn, ok, {"restricted_columns": len(restricted), "unmasked": short(leaks, 5)})
            tally["Restricted data masked"][0 if ok else 1] += 1

    for k, (p, f) in tally.items():
        print(f"{k:<26} pass {p:>3}  fail {f:>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
