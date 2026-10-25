"""Put every Toast API table and schema into the "Toast API" data product. Safe to rerun."""

from dh import gql, search_urns

products = search_urns(["DATA_PRODUCT"])
product = next(
    u for u in products
    if gql("query($u:String!){dataProduct(urn:$u){properties{name}}}", {"u": u})["dataProduct"]["properties"]["name"] == "Toast API"
)

platform = [{"field": "platform", "values": ["urn:li:dataPlatform:toast-api"]}]
assets = sorted(set(search_urns(["DATASET"], platform)) | set(search_urns(["CONTAINER"], platform)))

gql(
    "mutation($p: String!, $r: [String!]!) { batchSetDataProduct(input: {dataProductUrn: $p, resourceUrns: $r}) }",
    {"p": product, "r": assets},
)
print(f"Set data product {product} on {len(assets)} Toast API assets")
