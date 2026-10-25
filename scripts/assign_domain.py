"""Put every Toast API table and schema into the "Toast" domain. Safe to rerun."""

from dh import gql, search_urns

domains = gql("{ listDomains(input:{start:0,count:200}) { domains { urn properties { name } } } }")
domain = next(d["urn"] for d in domains["listDomains"]["domains"] if d["properties"]["name"] == "Toast")

platform = [{"field": "platform", "values": ["urn:li:dataPlatform:toast-api"]}]
assets = set(search_urns(["DATASET"], platform)) | set(search_urns(["CONTAINER"], platform))
inside = set(search_urns(["DATASET", "CONTAINER"], [{"field": "domains", "values": [domain]}]))
missing = sorted(assets - inside)

if missing:
    gql(
        "mutation($d: String!, $r: [ResourceRefInput!]!) { batchSetDomain(input: {domainUrn: $d, resources: $r}) }",
        {"d": domain, "r": [{"resourceUrn": u} for u in missing]},
    )
print(f"{len(assets)} Toast API assets; added {len(missing)} to the Toast domain ({domain})")
