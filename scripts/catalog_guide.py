"""Explain how to read Toast API tables: the Toast API data product description and a reading-guide document.

The column prefixes (query., path., response.) are kept on purpose: they show where each
column comes from in the API call. This script puts that explanation where people look:
the data product, a published guide document, and (via build_toast_metadata.py) every
table description and the Catalog Conventions glossary terms. Safe to rerun.
"""

from dh import gql, search_urns
from policies import upsert_doc

DATA_PRODUCT_DESC = """All 17 public Toast APIs (Orders, Labor, Menus, Restaurants, Configuration, Analytics and more) modeled as 60 tables in 7 business subdomains, with column descriptions, sample values, a Classification tier and privacy tags on every column, and business glossary terms on key fields. Feeds the Toast KPIs data product (GPV, Locations, average check, tip rate, labor cost %). Built from Toast's public OpenAPI specs.

**How to read the tables.** Each table is one API resource, such as `employees` or `orders`. Column names keep a prefix that shows where the column comes from in the API call:

| Prefix | Meaning | Example |
|---|---|---|
| `response.` | Data the API returns. Dots show nesting. This is the data that is classified and tagged. | `response.checks.customer.email` |
| `query.` | An option sent with the request: a filter, page size or flag. An input, not stored data. | `query.fetchRestaurantNames` |
| `path.` | An ID placed in the request URL, usually matching a `response.guid`. | `path.reportRequestGuid` |

Glossary terms: *Toast API table*, *Response field*, *Query parameter*, *Path parameter* (Toast Platform Glossary > Catalog Conventions). Full guide: *How to read Toast API tables* in Documents."""

GUIDE = """_How the Toast API catalog in DataHub is organized. Independent demo, not an official Toast document._

## One table per API resource
Toast publishes REST APIs, not database tables. Each resource in an API, such as `/labor/v1/employees`, becomes one table, and every endpoint on that resource contributes columns. The table's **Properties** tab lists the endpoints and counts its response fields, query parameters and path parameters.

## The three column prefixes

| Prefix | What it is | Example | Carries data? |
|---|---|---|---|
| `response.` | A field in what the API returns. Dots show nesting: `response.checks.customer.email` is the email on a check's customer. | `response.restaurantGuid` | Yes |
| `query.` | An option you send with the request to filter, page or shape the result. | `query.fetchRestaurantNames` (a flag to include restaurant names), `query.pageSize` | No, it is an input |
| `path.` | An identifier inside the request URL that selects one record. | `path.reportRequestGuid`, `path.employeeId` | No, it repeats an ID |

The prefixes are kept so that an engineer can map any column back to the exact part of the API call, and so that a reviewer can tell data from inputs at a glance.

## What this means for governance
- **Classification and privacy tags matter most on `response.` columns**, because those hold data about guests, employees and payments.
- **`query.` and `path.` columns are still classified**, usually Internal. Some carry identifiers, such as `path.employeeId` or `query.employeeIds`, and those carry the *PII: Indirect Identifier* tag.
- **Lineage starts from `response.` columns.** The Toast KPI model reads `response.amount`, `response.tipAmount` and similar fields, never request parameters.

## Glossary terms
Every column with a `query.` or `path.` prefix carries the *Query parameter* or *Path parameter* term. Every Toast API table carries the *Toast API table* term. *Response field* defines the `response.` prefix.
"""


def main() -> int:
    products = {gql("query($u:String!){dataProduct(urn:$u){properties{name}}}", {"u": u})["dataProduct"]["properties"]["name"]: u
                for u in search_urns(["DATA_PRODUCT"])}
    dp = products["Toast API"]
    gql("mutation($u: String!, $i: UpdateDataProductInput!) { updateDataProduct(urn: $u, input: $i) { urn } }",
        {"u": dp, "i": {"name": "Toast API", "description": DATA_PRODUCT_DESC}})
    print("updated  Toast API data product description")
    terms = [f"urn:li:glossaryTerm:toast.pg.{k}" for k in ("api_table", "response_field", "query_parameter", "path_parameter")]
    upsert_doc("toast-reading-api-tables", "How to read Toast API tables", GUIDE, [dp, *terms],
               owner="data-platform-engineering")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
