"""Shared DataHub GraphQL helper. Reads DATAHUB_GMS_URL and DATAHUB_TOKEN from the environment or .env."""

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

GMS = os.environ["DATAHUB_GMS_URL"].rstrip("/")
_HEADERS = {"Authorization": f"Bearer {os.environ['DATAHUB_TOKEN']}", "Content-Type": "application/json"}


def gql(query: str, variables: dict = None) -> dict:
    r = requests.post(f"{GMS}/api/graphql", headers=_HEADERS, json={"query": query, "variables": variables or {}}, timeout=120)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"], indent=1))
    return body["data"]


def search_urns(types: list, filters: list = None, query: str = "*") -> list:
    """Return every URN matching the search, paging through results."""
    q = """query($input: SearchAcrossEntitiesInput!) { searchAcrossEntities(input: $input) {
        total searchResults { entity { urn } } } }"""
    urns, start = [], 0
    while True:
        inp = {"types": types, "query": query, "start": start, "count": 200}
        if filters:
            inp["orFilters"] = [{"and": filters}]
        res = gql(q, {"input": inp})["searchAcrossEntities"]
        urns += [r["entity"]["urn"] for r in res["searchResults"]]
        start += 200
        if start >= res["total"]:
            return urns
