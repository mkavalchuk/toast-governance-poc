"""Create governance structured properties and set their values on Toast glossary terms and tables.

Properties:
  Certification Status   enum   glossary terms, tables, schemas   (Draft until an owner certifies it)
  Last Certified Date    date   glossary terms, tables             (set when the certification form is completed)
  Metric Type            enum   glossary terms
  Latest Reported Value  string glossary terms                     (from the most recent filing)
  Data Classification    enum   tables                             (highest column tier; shown as a badge)

Safe to rerun. Existing values set by people in the UI (for example a Certified status)
are kept; only empty properties are filled.
"""

import json
from pathlib import Path

from business_glossary import TERMS, term_urn
from dh import gql
from link_terms import DATA_TERMS

ROOT = Path(__file__).resolve().parent.parent
ET = "urn:li:entityType:datahub."


def sp(pid: str) -> str:
    return f"urn:li:structuredProperty:{pid}"


METRIC_TYPES = sorted({t[5]["metric_type"] for t in TERMS.values()} | {"Data element"})

PROPERTIES = [
    dict(id="toast.certificationStatus", displayName="Certification Status", valueType="string", cardinality="SINGLE",
         description="Where the definition stands in review. Owners move it from Draft to Certified through the certification form.",
         entityTypes=["glossaryTerm", "dataset", "container"],
         allowed=[("Draft", "Written but not yet reviewed by the owning functional unit."),
                  ("In Review", "The owning functional unit is reviewing the definition."),
                  ("Certified", "Approved by the owning functional unit and safe to use in reporting."),
                  ("Deprecated", "No longer in use; see the replacement term.")],
         settings=dict(showInSearchFilters=True, showInAssetSummary=True, showAsAssetBadge=True)),
    dict(id="toast.lastCertifiedDate", displayName="Last Certified Date", valueType="date", cardinality="SINGLE",
         description="Date the owner last certified this definition. Recertify after each quarterly filing.",
         entityTypes=["glossaryTerm", "dataset"], allowed=None,
         settings=dict(showInAssetSummary=True, hideInAssetSummaryWhenEmpty=False)),
    dict(id="toast.metricType", displayName="Metric Type", valueType="string", cardinality="SINGLE",
         description="What kind of business term this is, for example KPI, Non-GAAP measure or data element.",
         entityTypes=["glossaryTerm"], allowed=[(m, None) for m in METRIC_TYPES],
         settings=dict(showInSearchFilters=True, showInAssetSummary=True)),
    dict(id="toast.latestReportedValue", displayName="Latest Reported Value", valueType="string", cardinality="SINGLE",
         description="Most recent publicly reported value and period, from Toast's filings.",
         entityTypes=["glossaryTerm"], allowed=None,
         settings=dict(showInAssetSummary=True, hideInAssetSummaryWhenEmpty=True)),
    dict(id="toast.dataClassification", displayName="Data Classification", valueType="string", cardinality="SINGLE",
         description="Highest classification tier of any column in the table. Drives handling rules and access reviews.",
         entityTypes=["dataset"],
         allowed=[("Public", None), ("Internal", None), ("Confidential", None), ("Restricted", None)],
         settings=dict(showInSearchFilters=True, showInAssetSummary=True, showAsAssetBadge=True, showInColumnsTable=False)),
]


def create_properties():
    for p in PROPERTIES:
        inp = dict(
            id=p["id"], qualifiedName=p["id"], displayName=p["displayName"], description=p["description"],
            valueType=f"urn:li:dataType:datahub.{p['valueType']}", cardinality=p["cardinality"],
            entityTypes=[ET + e for e in p["entityTypes"]], settings=p["settings"],
        )
        if p["allowed"]:
            inp["allowedValues"] = [{"stringValue": v, **({"description": d} if d else {})} for v, d in p["allowed"]]
        try:
            gql("mutation($i: CreateStructuredPropertyInput!) { createStructuredProperty(input: $i) { urn } }", {"i": inp})
            print(f"created {p['displayName']}")
        except RuntimeError as e:
            if "already exists" not in str(e):
                raise
            print(f"exists  {p['displayName']}")


def current_values(urn: str) -> dict:
    sel = """structuredProperties { properties { structuredProperty { urn }
        values { ... on StringValue { stringValue } ... on NumberValue { numberValue } } } }"""
    q = f"""query($u: String!) {{ entity(urn: $u) {{
        ... on GlossaryTerm {{ {sel} }} ... on Dataset {{ {sel} }} ... on Container {{ {sel} }} }} }}"""
    ent = gql(q, {"u": urn})["entity"] or {}
    props = ((ent.get("structuredProperties") or {}).get("properties")) or []
    return {p["structuredProperty"]["urn"]: p["values"] for p in props}


# Derived from the columns on every build, so always overwritten rather than only filled.
DERIVED = {"toast.dataClassification"}


def fill(urn: str, wanted: dict):
    """Set empty properties and refresh derived ones, keeping anything people set in the UI."""
    have = current_values(urn)
    params = [{"structuredPropertyUrn": k, "values": v} for k, v in have.items()
              if k not in {sp(d) for d in DERIVED if wanted.get(d)}]
    added = 0
    for pid, value in wanted.items():
        if not value:
            continue
        current = [v.get("stringValue") for v in have.get(sp(pid), [])]
        if sp(pid) not in have or (pid in DERIVED and current != [value]):
            added += 1
        if sp(pid) not in have or pid in DERIVED:
            params.append({"structuredPropertyUrn": sp(pid), "values": [{"stringValue": value}]})
    if added:
        params = [{"structuredPropertyUrn": p["structuredPropertyUrn"],
                   "values": [{k: v for k, v in val.items() if v is not None} for val in p["values"]]} for p in params]
        gql("mutation($i: UpsertStructuredPropertiesInput!) { upsertStructuredProperties(input: $i) { properties { structuredProperty { urn } } } }",
            {"i": {"assetUrn": urn, "structuredPropertyInputParams": params}})
    return added


def main() -> int:
    create_properties()

    n = 0
    for key, t in TERMS.items():
        n += fill(term_urn(key), {"toast.certificationStatus": "Draft", "toast.metricType": t[5]["metric_type"],
                                  "toast.latestReportedValue": t[5].get("latest_reported_value")})
    for key in DATA_TERMS:
        n += fill(term_urn(key), {"toast.certificationStatus": "Draft", "toast.metricType": "Data element"})

    summary = json.loads((ROOT / "out" / "summary.json").read_text(encoding="utf-8"))
    for s in summary:
        n += fill(s["urn"], {"toast.certificationStatus": "Draft", "toast.dataClassification": s["top"]})
    print(f"Set {n} property values on {len(TERMS) + len(DATA_TERMS)} terms and {len(summary)} tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
