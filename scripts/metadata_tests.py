"""Create (or update) the Toast governance Metadata Tests and run them.

Property paths were checked with runTestDefinition against live assets:
  domains.domains, ownership.owners.owner, datasetProperties.description,
  glossaryTerms.terms.urn, dataProducts, structuredProperties.<property urn>

Tests that fail tag the asset with a "Needs ..." tag, and the tag is removed once
the asset passes, so open gaps are one search away.
"""

import json

from dh import gql, search_urns

PLATFORM = "urn:li:dataPlatform:toast-api"
CLASSES = [f"urn:li:glossaryTerm:Classification.{c}" for c in ("Public", "Internal", "Confidential", "Restricted")]
SP_CLASS = "structuredProperties.urn:li:structuredProperty:toast.dataClassification"
SP_CERT = "structuredProperties.urn:li:structuredProperty:toast.certificationStatus"

TAGS = {
    "needs-owner": ("Needs Owner", "#E5484D", "Added by the 'table has an owner' metadata test."),
    "needs-classification": ("Needs Classification", "#F76B15", "Added by the 'table is classified' metadata test."),
    "needs-domain": ("Needs Domain", "#FFB224", "Added by the 'asset is in a domain' metadata test."),
}


def on(types, *extra):
    return {"types": types, "conditions": {"and": [
        {"property": "dataPlatformInstance.platform", "operator": "equals", "values": [PLATFORM]}, *extra]}}


def tag_actions(tag):
    urn = f"urn:li:tag:{tag}"
    return {"passing": [{"type": "remove_tags", "values": [urn]}], "failing": [{"type": "add_tags", "values": [urn]}]}


TESTS = [
    ("toast-table-has-owner", "Toast API tables have an owner", "Ownership",
     "Every Toast API table needs at least one owner who answers questions and approves access.",
     {"on": on(["dataset"]), "rules": {"and": [{"property": "ownership.owners.owner", "operator": "exists"}]},
      "actions": tag_actions("needs-owner")}),
    ("toast-asset-has-domain", "Toast API tables and schemas are in a domain", "Ownership",
     "Domains define accountability. Assets outside a domain have no clear governing team.",
     {"on": on(["dataset", "container"]), "rules": {"and": [{"property": "domains.domains", "operator": "exists"}]},
      "actions": tag_actions("needs-domain")}),
    ("toast-asset-in-data-product", "Toast API assets belong to the Toast API data product", "Data Products",
     "Every table and schema from the Toast API should be published as part of the Toast API data product.",
     {"on": on(["dataset", "container"]), "rules": {"and": [{"property": "dataProducts", "operator": "exists"}]}}),
    ("toast-table-has-description", "Toast API tables have a description", "Documentation",
     "A table without a description cannot be found or understood by consumers.",
     {"on": on(["dataset"]), "rules": {"and": [{"property": "datasetProperties.description", "operator": "exists"}]}}),
    ("toast-table-is-classified", "Toast API tables are classified", "Compliance",
     "Each table carries one Classification glossary term and a matching Data Classification property.",
     {"on": on(["dataset"]), "rules": {"and": [
         {"property": "glossaryTerms.terms.urn", "operator": "equals", "values": CLASSES},
         {"property": SP_CLASS, "operator": "exists"}]},
      "actions": tag_actions("needs-classification")}),
    ("toast-restricted-table-certified", "Restricted Toast API tables are certified", "Compliance",
     "Tables holding Restricted data (card, contact, credential or pay data) must be certified by their owner. "
     "Failing tables form the review queue for the Restricted Data Attestation form.",
     {"on": on(["dataset"], {"property": SP_CLASS, "operator": "equals", "values": ["Restricted"]}),
      "rules": {"and": [{"property": SP_CERT, "operator": "equals", "values": ["Certified"]}]}}),
    ("toast-restricted-table-owned", "Restricted Toast API tables have an owner", "Compliance",
     "Restricted data needs a named accountable owner before anyone can be granted access.",
     {"on": on(["dataset"], {"property": SP_CLASS, "operator": "equals", "values": ["Restricted"]}),
      "rules": {"and": [{"property": "ownership.owners.owner", "operator": "exists"}]}}),
]


def ensure_tags():
    for tid, (name, color, desc) in TAGS.items():
        try:
            gql("mutation($i: CreateTagInput!) { createTag(input: $i) }", {"i": {"id": tid, "name": name, "description": desc}})
        except RuntimeError as e:
            if "already exists" not in str(e):
                raise
        gql("mutation($u: String!, $c: String!) { setTagColor(urn: $u, colorHex: $c) }", {"u": f"urn:li:tag:{tid}", "c": color})


def upsert_tests() -> list:
    existing = {t["urn"] for t in gql("{ listTests(input:{start:0,count:500}) { tests { urn } } }")["listTests"]["tests"]}
    urns = []
    for tid, name, category, desc, definition in TESTS:
        urn = f"urn:li:test:{tid}"
        body = {"name": name, "category": category, "description": desc, "definition": {"json": json.dumps(definition)}}
        if urn in existing:
            gql("mutation($u: String!, $i: UpdateTestInput!) { updateTest(urn: $u, input: $i) }", {"u": urn, "i": body})
        else:
            gql("mutation($i: CreateTestInput!) { createTest(input: $i) }", {"i": {"id": tid, **body}})
        urns.append(urn)
        print(f"{'updated' if urn in existing else 'created'}  {name}")
    return urns


def main() -> int:
    ensure_tags()
    upsert_tests()
    # On-demand runs of a whole test are disabled on this instance (metadataTests.onDemand.enabled=false),
    # so evaluate every Toast asset directly. runTests(asset) also applies the tag actions.
    platform = [{"field": "platform", "values": [PLATFORM]}]
    assets = search_urns(["DATASET"], platform) + search_urns(["CONTAINER"], platform)
    for urn in assets:
        gql("mutation($u: String!) { runTests(urn: $u) }", {"u": urn})
    print(f"Evaluated all tests on {len(assets)} Toast assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
