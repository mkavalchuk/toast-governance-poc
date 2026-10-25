"""Check what DataHub holds for the Toast API platform: schemas, tables, columns, terms."""

import json
import os
import sys
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

GMS = os.environ["DATAHUB_GMS_URL"].rstrip("/")
HEADERS = {"Authorization": f"Bearer {os.environ['DATAHUB_TOKEN']}", "Content-Type": "application/json"}


def gql(query: str, variables: dict) -> dict:
    r = requests.post(f"{GMS}/api/graphql", headers=HEADERS, json={"query": query, "variables": variables}, timeout=60)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise SystemExit(json.dumps(body["errors"], indent=1))
    return body["data"]


SEARCH = """
query($start: Int!) {
  searchAcrossEntities(input: {types: [DATASET], query: "*", start: $start, count: 100,
      orFilters: [{and: [{field: "platform", values: ["urn:li:dataPlatform:toast-api"]}]}]}) {
    total
    searchResults { entity { urn ... on Dataset {
      properties { name }
      container { properties { name } }
      glossaryTerms { terms { term { properties { name } } } }
      schemaMetadata { fields { fieldPath glossaryTerms { terms { term { urn } } } } }
      datasetProfiles(limit: 1) { fieldProfiles { fieldPath sampleValues } }
    } } }
  }
}"""

data = gql(SEARCH, {"start": 0})["searchAcrossEntities"]
rows = data["searchResults"]
print(f"Datasets on platform toast-api: {data['total']}")

tiers, missing_terms, cols, samples, by_schema = Counter(), 0, 0, 0, Counter()
for r in rows:
    e = r["entity"]
    fields = (e.get("schemaMetadata") or {}).get("fields") or []
    cols += len(fields)
    by_schema[(e.get("container") or {}).get("properties", {}).get("name", "NO CONTAINER")] += 1
    for f in fields:
        terms = (f.get("glossaryTerms") or {}).get("terms") or []
        if terms:
            tiers[terms[0]["term"]["urn"].split(".")[-1]] += 1
        else:
            missing_terms += 1
    prof = (e.get("datasetProfiles") or [{}])
    samples += sum(1 for p in (prof[0].get("fieldProfiles") or []) if p.get("sampleValues")) if prof else 0

print(f"Columns: {cols}  with sample values: {samples}  without a classification term: {missing_terms}")
print("Column tiers:", dict(tiers))
print("Tables per schema:", dict(sorted(by_schema.items())))

GLOSSARY = """query { glossaryNode(urn: "urn:li:glossaryNode:Classification") {
  properties { name } children: relationships(input: {types: ["IsPartOf"], direction: INCOMING, start: 0, count: 10}) {
    relationships { entity { ... on GlossaryTerm { properties { name } } } } } } }"""
node = gql(GLOSSARY, {})["glossaryNode"]
print("Classification terms:", [x["entity"]["properties"]["name"] for x in node["children"]["relationships"]])

for r in rows:
    if r["entity"]["urn"].endswith("labor.employees,PROD)"):
        print("Labor.employees URN:", r["entity"]["urn"])
sys.exit(0)
