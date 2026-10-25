# Screenshots for the portfolio page

Independent project, not affiliated with Toast. The KPI model and policy documents are illustrative.
DataHub links open the DataHub Cloud trial, which needs a login and stops working when the trial ends.

Base URL: https://smart-gannet-2f4400.trials.acryl.io

## AI-assisted discovery

| Screenshot | Caption | DataHub link |
|---|---|---|
| `01-ask-datahub-gpv-answer.jpg` | Ask DataHub reads the KPI model's SQL and lineage and explains GPV as amount plus tip for Toast-processed payments, excluding voids. | /ai-chat |
| `02-ask-datahub-gpv-owner.jpg` | The answer cites the GPV glossary term, its 10-K definition and the accountable owner, Fintech & Payments. | /ai-chat |

## Privacy and classification

| Screenshot | Caption | DataHub link |
|---|---|---|
| `08-pii-tags-servername.jpg` | A server's name carries PII, Direct Identifier and Data Subject: Employee tags plus a Confidential tier. Rules read the column and its parent object, so a restaurant's own phone number is not tagged. | /dataset/urn:li:dataset:(urn:li:dataPlatform:toast-api,analytics.check,PROD)/Columns?highlightedPath=response.serverName |
| `17-guest-email-pii-tags.jpg` | A guest's email is Restricted, tagged PII and Data Subject: Guest, and linked to the Guest Contact Info term. | /dataset/urn:li:dataset:(urn:li:dataPlatform:toast-api,orders.checks,PROD)/Columns?highlightedPath=response.customer.email |
| `18-guest-email-masked.jpg` | Sample values for Restricted columns are masked, and a monitor checks it on every Restricted table. | same as above |
| `19-guest-data-search.jpg` | One tag filter lists every table holding guest personal data, the starting point for an access or deletion request. | /search?filter__entityType___false___EQUAL___1=DATASET&filter_tags___false___EQUAL___0=urn%3Ali%3Atag%3Adata-subject-guest&page=1&query=&unionType=0 |
| `10-classification-policy.jpg` | Four tiers with handling rules, plus the privacy tags that sit alongside them. | /document/urn:li:document:toast-data-classification-policy |

## Lineage and KPI calculations

| Screenshot | Caption | DataHub link |
|---|---|---|
| `03-gpv-lineage.jpg` | Orders payments and Restaurants flow through staging, marts and the GPV model into the GPV trend chart. | /dataset/urn:li:dataset:(urn:li:dataPlatform:dbt,toast_kpi.kpi.kpi_gpv_daily,PROD)/Lineage |
| `05-kpi-gpv-sql.jpg` | Each model carries its SQL, so the definition of GPV is inspectable next to the data. | /dataset/urn:li:dataset:(urn:li:dataPlatform:dbt,toast_kpi.kpi.kpi_gpv_daily,PROD)/View%20Definition |
| `04-kpi-gpv-columns.jpg` | The gpv column carries the GPV glossary term and a Confidential tier; descriptions state the calculation. | /dataset/urn:li:dataset:(urn:li:dataPlatform:dbt,toast_kpi.kpi.kpi_gpv_daily,PROD)/Columns |
| `15-kpi-dashboard-lineage.jpg` | Five KPI charts traced to the models that feed them. | /dashboard/urn:li:dashboard:(looker,restaurant_performance_kpis)/Lineage |

## Business glossary

| Screenshot | Caption | DataHub link |
|---|---|---|
| `09-glossary-gpv-term.jpg` | KPIs, non-GAAP measures and revenue streams from Toast's filings, each with a source, owner by functional unit and certification status. | /glossaryTerm/urn:li:glossaryTerm:toast.gpv |
| `20-query-parameter-term.jpg` | All 112 Toast Platform Guide terms plus Toast's API objects, linked to the tables and columns they describe. Catalog Conventions terms explain the column prefixes. | /glossaryTerm/urn:li:glossaryTerm:toast.pg.query_parameter |

## Reading the catalog

| Screenshot | Caption | DataHub link |
|---|---|---|
| `13-data-product-column-guide.jpg` | 77 tables and schemas published as one data product, with a guide to the query., path. and response. column prefixes. | /dataProduct/urn:li:dataProduct:c1d8e5b4-1161-48e5-b1b1-c125fe8f5673 |
| `21-reading-guide.jpg` | response. columns hold data; query. and path. columns are request inputs. The guide explains what that means for governance. | /document/urn:li:document:toast-reading-api-tables |

## Ownership and organization

| Screenshot | Caption | DataHub link |
|---|---|---|
| `12-subdomain-orders-payments.jpg` | Seven business subdomains model accountability across API boundaries. | /domain/urn:li:domain:toast-orders-payments |
| `11-access-policy-restricted.jpg` | Access policies target tables by their Data Classification property. | /settings/permissions/policies |

## Automation and monitoring

| Screenshot | Caption | DataHub link |
|---|---|---|
| `14-metadata-tests.jpg` | Seven rules check ownership, domains, classification and certification. | /tests |
| `06-payments-governance-tests.jpg` | Test results on a table: six standards pass, owner certification is open. | /dataset/urn:li:dataset:(urn:li:dataPlatform:toast-api,orders.payments,PROD)/Governance |
| `07-payments-quality-assertions.jpg` | Monitors for schema drift against Toast's live specs, classification coverage and masking. | /dataset/urn:li:dataset:(urn:li:dataPlatform:toast-api,orders.payments,PROD)/Quality |
| `16-compliance-forms.jpg` | KPI Certification and Restricted Data Attestation forms route review tasks to owners. | /govern/dashboard?documentationTab=forms |
| `22-restricted-awaiting-verification.jpg` | A Restricted table shows Awaiting Verification until its owner completes the attestation. | /dataset/urn:li:dataset:(urn:li:dataPlatform:toast-api,orders.checks,PROD)/Summary |
