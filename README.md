# Toast data governance proof of concept

A working data governance program for Toast's public APIs, built in DataHub Cloud. It catalogs all 17 public Toast APIs, classifies every column, tags personal and card data, defines Toast's KPIs and vocabulary in a business glossary, links that glossary to the data, and automates the checks that keep it accurate.

This is an independent project. It is not affiliated with, endorsed by or built with any non-public information from Toast. Everything is derived from Toast's public API specifications, the Toast Platform Guide and Toast's SEC filings.

**Live demo:** the catalog runs in a DataHub Cloud instance that requires a login. Request access, or just check out some screenshots, by navigating to [mike-kav.com/toast] and sending an email.

## What it shows

| Area | What is in DataHub |
|---|---|
| Catalog | 17 Toast APIs as 17 schemas and 60 tables with 3,281 columns, descriptions and sample values |
| Organization | A Toast domain with 7 business subdomains, a Toast API data product and a Toast KPIs data product |
| Ownership | A business owner by functional unit, a technical owner, and a Legal & Compliance data steward on every table that is Restricted or holds personal data |
| Classification | One tier (Public, Internal, Confidential, Restricted) on every column; the highest tier rolls up to the table as a structured property |
| Privacy tags | PII, PII: Direct Identifier, PII: Indirect Identifier, PCI: Card Data, Credential, Compensation, and Data Subject: Guest or Employee, on 226 columns in 15 tables |
| Business glossary | About 200 terms: KPIs and financial measures from Toast's 10-K, S-1 and earnings releases; all 112 Toast Platform Guide glossary entries; Toast's API objects; operational data terms; catalog conventions |
| Glossary links | Terms attached to 50 tables and more than 750 columns, so a KPI such as GPV leads to the exact fields behind it |
| Lineage | An illustrative dbt model (staging, marts, KPIs) and a KPI dashboard, with column-level lineage and the SQL for each calculation |
| Access | Policies that target tables by their Data Classification, a Data Classification Policy and a Data Access Policy |
| Automation | 7 metadata tests, 2 compliance forms (KPI certification, Restricted data attestation) and 134 governance assertions (schema drift against Toast's live specs, classification coverage, masking) |

## Architecture

```
Toast public sources                    scripts/                                  DataHub Cloud
--------------------                    --------                                  -------------
17 API specs (doc.toasttab.com)  --->   build_toast_metadata.py  ------------->   Toast API platform, schemas, tables,
                                        (columns, tiers, privacy tags)            columns, tags, sample values
10-K, S-1, earnings releases     --->   business_glossary.py     ------------->   Toast Business Glossary, owner groups
Toast Platform Guide glossary    --->   platform_glossary.py     ------------->   Toast Platform Glossary, table and column links
                                        link_terms.py                             Operational data terms on columns
                                        lineage_model.py                          dbt KPI model, dashboard, lineage
                                        subdomains_owners.py, term_domains.py,    Domains, subdomains, owners, stewards,
                                        assign_data_product.py                    data products
                                        structured_properties.py                  Certification and classification properties
                                        compliance_forms.py, policies.py          Forms, access policies, policy documents
                                        metadata_tests.py, monitor.py             Metadata tests, custom assertions
```

### How to read the tables
Each table is one API resource, such as `employees`. Column names keep a prefix that shows where the column comes from in the API call:

| Prefix | Meaning | Example |
|---|---|---|
| `response.` | Data the API returns. Dots show nesting. | `response.checks.customer.email` |
| `query.` | An option sent with the request, such as a filter or flag. Not stored data. | `query.fetchRestaurantNames` |
| `path.` | An ID placed in the request URL. | `path.reportRequestGuid` |

### Classification and tags
Tiers say how to handle data. Tags say what the data is and whose it is. Rules look at a column's name and its parent object, so `customer.phone` is guest PII while a restaurant's own `location.phone` is business data. A pseudonymous ID such as `server.guid` stays Internal but carries the PII: Indirect Identifier tag.

## Run it yourself

Requires Python 3.11 or later and a DataHub instance (DataHub Cloud, or open source DataHub via `datahub docker quickstart`). Built and tested with acryl-datahub 1.7.0.17.

```bash
python -m venv .venv
.venv/Scripts/activate        # on macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then set DATAHUB_GMS_URL and DATAHUB_TOKEN
python scripts/download_specs.py
python scripts/sync_all.py
```

`sync_all.py` runs every step in dependency order and is safe to rerun. Each script also runs on its own; most print a plan without `--push` and write to DataHub with it. `monitor.py` can run on a schedule to catch new Toast API releases.

Before the first run, create a domain named `Toast` and a data product named `Toast API` in DataHub; the scripts attach everything to them.

## Repository layout

| Path | Contents |
|---|---|
| `scripts/` | All build, glossary, governance and monitoring scripts |
| `screenshots/` | Screenshot gallery (`gallery.html`) and captions (`SCREENSHOTS.md`) |
| `specs/` | Toast API specs, downloaded by `download_specs.py` and not committed |
| `out/` | Generated metadata, not committed |

## Notes and limitations
- The KPI model is illustrative. Its formulas approximate the public definitions in Toast's filings; Toast's internal calculations are not public.
- Glossary definitions are written in our own words and link back to their sources.
- Sample values are taken from the spec examples where they exist and are synthetic otherwise. Restricted columns are always masked.
- Toast's specs chain `allOf` references more deeply than DataHub's built-in OpenAPI source resolves, so this project builds the schemas itself instead of using that source.

## Screenshots
See the [gallery](screenshots/gallery.html), or the captions and links in [SCREENSHOTS.md](screenshots/SCREENSHOTS.md).
