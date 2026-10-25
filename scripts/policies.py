"""Create Toast access policies and publish the Classification and Access policy documents.

DataHub policies are additive (they grant, never deny). Least-privilege for Restricted data
also requires narrowing the built-in "All Users - View Dataset Sensitive Information" policy;
this script does not change built-in policies. Safe to rerun: policies are matched by name.
"""

from dh import gql

SP_CLASS = "urn:li:structuredProperty:toast.dataClassification"
TOAST_DOMAINS = ["urn:li:domain:" + d for d in (
    "toast-restaurant-location", "toast-guest", "toast-orders-payments", "toast-labor-payroll",
    "toast-menu", "toast-finance-metrics", "toast-platform-integrations")]
G = "urn:li:corpGroup:"

RESTRICTED = {"criteria": [
    {"field": "TYPE", "condition": "EQUALS", "values": ["dataset"]},
    {"field": "STRUCTURED_PROPERTY", "condition": "EQUALS", "values": ["Restricted"],
     "structuredPropertyValues": {"propertyUrn": SP_CLASS, "values": ["Restricted"]}},
]}

POLICIES = [
    dict(name="Toast - Restricted data: steward controls",
         description="Legal & Compliance and each table's Data Steward control classification, tags, terms and documentation "
                     "on tables whose Data Classification is Restricted.",
         resources={"filter": RESTRICTED},
         privileges=["EDIT_ENTITY_GLOSSARY_TERMS", "EDIT_DATASET_COL_GLOSSARY_TERMS", "EDIT_ENTITY_TAGS", "EDIT_DATASET_COL_TAGS",
                     "EDIT_ENTITY_PROPERTIES", "EDIT_DATASET_COL_PROPERTIES", "EDIT_ENTITY_DOCS", "EDIT_DATASET_COL_DESCRIPTION",
                     "EDIT_DEPRECATION_PRIVILEGE", "CERTIFY_ENTITY"],
         actors={"groups": [G + "legal-compliance"], "resourceOwners": True,
                 "resourceOwnersTypes": ["urn:li:ownershipType:__system__data_steward"]}),
    dict(name="Toast - Restricted data: sample and profile access",
         description="Only Legal & Compliance and the table's owners may view profiles, sample values and usage for Restricted "
                     "tables. Pair with narrowing the built-in 'All Users - View Dataset Sensitive Information' policy.",
         resources={"filter": RESTRICTED},
         privileges=["VIEW_DATASET_PROFILE", "VIEW_DATASET_USAGE", "VIEW_DATASET_OPERATIONS"],
         actors={"groups": [G + "legal-compliance"], "resourceOwners": True}),
    dict(name="Toast - Domain owners manage their assets",
         description="Business and technical owners maintain documentation, ownership, lineage and quality checks for the "
                     "assets in the Toast subdomains they own.",
         resources={"filter": {"criteria": [{"field": "DOMAIN", "condition": "EQUALS", "values": TOAST_DOMAINS}]}},
         privileges=["EDIT_ENTITY_DOCS", "EDIT_DATASET_COL_DESCRIPTION", "EDIT_ENTITY_OWNERS", "EDIT_LINEAGE",
                     "EDIT_ENTITY_ASSERTIONS", "EDIT_ENTITY_INCIDENTS", "EDIT_ENTITY_DOC_LINKS", "EDIT_ENTITY_DATA_PRODUCTS"],
         actors={"resourceOwners": True}),
    dict(name="Toast - Finance certifies KPI definitions",
         description="FP&A and Accounting & SEC Reporting edit and certify KPI, non-GAAP and revenue definitions in the "
                     "Finance and Metrics subdomain.",
         resources={"filter": {"criteria": [
             {"field": "TYPE", "condition": "EQUALS", "values": ["glossaryTerm"]},
             {"field": "DOMAIN", "condition": "EQUALS", "values": ["urn:li:domain:toast-finance-metrics"]}]}},
         privileges=["EDIT_ENTITY_DOCS", "EDIT_ENTITY_PROPERTIES", "EDIT_ENTITY_OWNERS", "CERTIFY_ENTITY", "MANAGE_ENTITY_FORMS"],
         actors={"groups": [G + "finance-fpa", G + "finance-accounting"], "resourceOwners": True}),
]


def upsert_policies():
    existing = {p["name"]: p["urn"] for p in
                gql("{ listPolicies(input:{start:0,count:500}) { policies { urn name } } }")["listPolicies"]["policies"]}
    urns = []
    for p in POLICIES:
        inp = {"type": "METADATA", "name": p["name"], "description": p["description"], "state": "ACTIVE",
               "privileges": p["privileges"],
               "actors": {"allUsers": False, "allGroups": False, "resourceOwners": False, **p["actors"]},
               "resources": {"allResources": False, **p["resources"]}}
        if p["name"] in existing:
            gql("mutation($u: String!, $i: PolicyUpdateInput!) { updatePolicy(urn: $u, input: $i) }", {"u": existing[p["name"]], "i": inp})
            urns.append(existing[p["name"]])
            print(f"updated  {p['name']}")
        else:
            urns.append(gql("mutation($i: PolicyUpdateInput!) { createPolicy(input: $i) }", {"i": inp})["createPolicy"])
            print(f"created  {p['name']}")
    return urns


CLASSIFICATION_DOC = """_Illustrative policy written for a DataHub governance demo. Not an official Toast document._

## Purpose
Every Toast API table and column carries one classification tier. The tier decides who can see the data, how it is stored and how it may be shared. Classification is recorded in DataHub as a **Classification** glossary term on each column and as the **Data Classification** property on each table (the highest tier of any column).

## Tiers

| Tier | Examples | Handling |
|---|---|---|
| **Public** | Menu item names, descriptions and prices | No restrictions beyond accuracy. |
| **Internal** | GUIDs, timestamps, configuration, order counts | Employees and authorized partners only. Do not publish externally. |
| **Confidential** | Sales and payment amounts, tips, guest and employee names, addresses | Need-to-know access. Never in logs or broad analytics extracts without owner approval. |
| **Restricted** | Card data (PCI), guest contact info (CCPA, GDPR), wages, credentials | Encrypt at rest, mask in non-production and sample data, access limited to named roles, Data Steward assigned. |

## Privacy tags
Tiers say **how** to handle data. Tags say **what** the data is and **whose** it is, so a privacy request or audit can find it with one search filter. Tags sit on each column and roll up to the table.

| Tag | Applied to | Examples |
|---|---|---|
| **PII** | Any personal data about a guest or employee | All of the below |
| **PII: Direct Identifier** | Identifies a person on its own | `customer.email`, `serverName`, `tabName`, delivery address and coordinates |
| **PII: Indirect Identifier** | Pseudonymous IDs that identify a person when joined | `server.guid`, `employeeReference`, `customer.guid` |
| **PCI: Card Data** | Card attributes | `cardType`, `last4Digits`, `first6Digits` |
| **Credential** | Secrets | access and refresh tokens, passcodes |
| **Compensation** | Pay and tips paid to employees | `hourlyWage`, `wageOverrides.wage`, `nonCashTips` |
| **Data Subject: Guest / Employee** | Whose personal data it is | Used to answer access and deletion requests |

A restaurant's own published phone number and address are business data and are not tagged PII. Indirect identifiers keep their tier (often Internal) but carry the PII tag, because pseudonymous data is still personal data under GDPR.

## Rules
1. **Highest tier wins.** A table takes the highest tier of any column it holds.
2. **Derived data can step down.** Aggregates may take a lower tier than their inputs when they no longer identify a person or card. Example: `fct_labor_cost.labor_cost` is Confidential although it is derived from Restricted `hourly_wage`. The data owner documents the reason.
3. **Restricted columns are never shown unmasked** in sample values. The *Restricted data masked* assertion checks this on every Restricted table.
4. **New columns are classified before release.** The *Classification coverage* assertion and the *Toast API tables are classified* metadata test fail until they are.
5. **Restricted tables are certified.** Owners complete the *Restricted Data Attestation* form; the *Restricted Toast API tables are certified* test tracks completion.

## Roles
- **Business Owner** (by subdomain) approves access and certifies the classification.
- **Data Steward** (Legal & Compliance) owns the tier definitions and handling rules and is assigned to every Restricted table and every table tagged PII.
- **Technical Owner** (Data Platform Engineering) implements masking, encryption and monitoring.

## Review
Recertify Restricted tables and KPI definitions after each quarterly filing, using the compliance forms in DataHub.
"""

ACCESS_DOC = """_Illustrative policy written for a DataHub governance demo. Not an official Toast document._

## Principles
- **Least privilege.** Access follows the Data Classification of the table, not the person's team.
- **Owners approve.** The Business Owner of the subdomain approves access to Confidential and Restricted data.
- **Stewards control sensitive metadata.** Classification, tags and terms on Restricted tables are edited only by Legal & Compliance and the table's Data Steward.

## How it is enforced in DataHub

| DataHub policy | Who | What |
|---|---|---|
| Toast - Restricted data: steward controls | Legal & Compliance, Data Stewards | Edit terms, tags, properties and docs on tables classified Restricted |
| Toast - Restricted data: sample and profile access | Legal & Compliance, table owners | View profiles, sample values and usage of Restricted tables |
| Toast - Domain owners manage their assets | Owners of assets in the Toast subdomains | Maintain docs, ownership, lineage, assertions and incidents |
| Toast - Finance certifies KPI definitions | FP&A, Accounting & SEC Reporting | Edit and certify KPI, non-GAAP and revenue terms |

Policies target tables by the **Data Classification** structured property, so a table that is reclassified to Restricted is covered the moment its property changes. No policy needs to list tables by name.

## Access levels by tier

| Tier | Default access | Approval |
|---|---|---|
| Public | Everyone | None |
| Internal | All employees | None |
| Confidential | Role-based, by subdomain | Business Owner |
| Restricted | Named roles only, time-bound | Business Owner and Data Steward |

## Gaps to close in production
DataHub policies grant and never deny. The built-in *All Users - View Dataset Sensitive Information* policy must be narrowed so that the Restricted sample and profile policy is the only path to that data.
"""


def upsert_doc(doc_id, title, text, related, owner="legal-compliance"):
    try:
        gql("mutation($i: CreateDocumentInput!) { createDocument(input: $i) }", {"i": {
            "id": doc_id, "title": title, "state": "PUBLISHED", "contents": {"text": text}, "relatedAssets": related,
            "owners": [{"ownerUrn": G + owner, "ownerEntityType": "CORP_GROUP", "type": "BUSINESS_OWNER"}],
            "settings": {"showInGlobalContext": True}}})
        print(f"created  document {title}")
    except RuntimeError as e:
        if "already exists" not in str(e):
            raise
        urn = f"urn:li:document:{doc_id}"
        gql("mutation($i: UpdateDocumentContentsInput!) { updateDocumentContents(input: $i) }",
            {"i": {"urn": urn, "title": title, "contents": {"text": text}}})
        gql("mutation($i: UpdateDocumentRelatedEntitiesInput!) { updateDocumentRelatedEntities(input: $i) }",
            {"i": {"urn": urn, "relatedAssets": related}})
        print(f"updated  document {title}")


def main() -> int:
    upsert_policies()
    tiers = [f"urn:li:glossaryTerm:Classification.{t}" for t in ("Public", "Internal", "Confidential", "Restricted")]
    upsert_doc("toast-data-classification-policy", "Toast Data Classification Policy", CLASSIFICATION_DOC,
               tiers + ["urn:li:glossaryTerm:toast.card_data", "urn:li:glossaryTerm:toast.guest_contact_info", "urn:li:glossaryTerm:toast.wage"])
    upsert_doc("toast-data-access-policy", "Toast Data Access Policy", ACCESS_DOC,
               ["urn:li:glossaryTerm:Classification.Restricted", "urn:li:glossaryTerm:Classification.Confidential",
                "urn:li:domain:a9e7c91d-16b1-4a5a-9cfd-d88a80de5f06"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
