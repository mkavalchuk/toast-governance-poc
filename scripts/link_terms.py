"""Create operational data terms and link business terms to specific Toast API columns.

Each operational term:
  - sits in Toast Business Glossary > Operational Data Terms,
  - inherits (IsA) its Classification tier, e.g. Card Data IsA Restricted,
  - relates to the KPI or business term it feeds, e.g. Payment Amount -> GPV,
  - is attached to every column whose path matches its rule.

Columns that identify a restaurant or restaurant group are linked straight to the
existing Location and Customer KPI terms.

    python scripts/link_terms.py            # print the column mapping only
    python scripts/link_terms.py --push     # create terms and apply the links
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import (
    DomainsClass,
    GlossaryNodeInfoClass,
    GlossaryRelatedTermsClass,
    GlossaryTermInfoClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
)

from business_glossary import GROUPS, ROOT_NODE, term_urn

ROOT = Path(__file__).resolve().parent.parent
NODE = "urn:li:glossaryNode:toast_data"
API_DOCS = "https://doc.toasttab.com/openapi/"
ADMIN_GLOSSARY = "https://doc.toasttab.com/doc/platformguide/adminGlossary.html"
# Terms whose definition follows the Toast Platform Guide glossary rather than the API docs.
FROM_ADMIN_GLOSSARY = {"tip", "gratuity", "net_sales", "gross_sales"}


def tier(level: str) -> str:
    return f"urn:li:glossaryTerm:Classification.{level}"


# key: (name, owner, classification, definition, related business terms, leaf regex, context regex or None)
# The leaf regex must match the column's last path segment exactly. The context regex is
# searched in "<table>::<field path>", e.g. "orders.orders::response.checks.payments.amount".
DATA_TERMS = {
    "payment_amount": ("Payment Amount", "fintech-payments", "Confidential",
                       "The amount of a single payment applied to a check, before tip. Summed across Toast Processing Locations it is the basis of GPV.",
                       ["gpv", "financial_technology_solutions"], r"amount|amountTendered",
                       r"payments\.(amount|amountTendered)$|orders\.payments::response\.|creditcards"),
    "tip": ("Tip", "fintech-payments", "Confidential",
            "An amount the guest chooses to add on top of the bill for the server or delivery driver, who owes any tax on it. "
            "Paid out to employees through payroll, tip out or PayOut.",
            ["toast_payout", "gpv"], r"tipAmount|checkTipAmount", None),
    "gratuity": ("Gratuity", "fintech-payments", "Confidential",
                 "A service charge the restaurant sets and adds to the bill, for example an automatic charge for a large party, "
                 "then pays to the employee responsible for the check.",
                 ["tip"], r"gratuity|gratuityAmount|checkGratuityAmount", None),
    "check_total": ("Check Total", "product-management", "Internal",
                    "The amount due on a check. Check amount excludes tax and tip; total amount includes tax.",
                    ["payment_amount"], r"checkTotalAmount|totalAmount|amount",
                    r"::response\.(orders\.)?checks\.(amount|totalAmount)$|orders\.checks::response\.(amount|totalAmount)$|analytics\.check::"),
    "net_sales": ("Net Sales", "finance-fpa", "Confidential",
                  "Toast's reporting measure of income after deductions: what guests paid for items sold plus non-gratuity service "
                  "charges kept by the restaurant, after discounts, customer credits and refunds. Returned by the Analytics API.",
                  ["gross_sales", "discount_amount", "refund_amount"], r"netSalesAmount", None),
    "gross_sales": ("Gross Sales", "finance-fpa", "Confidential",
                    "Net sales plus discounts: the value of items and non-gratuity services sold before deductions.",
                    ["net_sales"], r"grossSalesAmount", None),
    "discount_amount": ("Discount Amount", "product-management", "Internal",
                        "Value of a discount applied to a check or item.",
                        ["net_sales"], r"discountAmount|checkDiscountAmount", None),
    "refund_amount": ("Refund Amount", "fintech-payments", "Confidential",
                      "Value returned to a guest against a prior payment.",
                      ["net_sales", "payment_amount"], r"refundAmount|checkRefundAmount", None),
    "menu_item_price": ("Menu Item Price", "product-management", "Public",
                        "The price a guest sees for a menu item or modifier before discounts and tax.",
                        ["subscription_services"], r"price|basePrice", r"^menus|^configuration|selections\.price$"),
    "guest_contact_info": ("Guest Contact Info", "legal-compliance", "Restricted",
                           "Name, email and phone of a guest attached to a check. Personal data under CCPA and GDPR; use only for the purpose the guest gave it.",
                           ["customer"], r"firstName|lastName|email|phone", r"customer\."),
    "card_data": ("Card Data", "legal-compliance", "Restricted",
                  "Payment card attributes such as card brand and last four digits. In PCI DSS scope; never store full card numbers.",
                  ["payment_amount"], r"last4Digits|cardLast4Digits|cardType|paymentCardType", None),
    "employee_personal_data": ("Employee Personal Data", "legal-compliance", "Restricted",
                               "Name, email and phone of a restaurant employee. Personal data; access limited to HR and payroll roles.",
                               ["toast_payroll"], r"firstName|lastName|chosenName|email|phoneNumber|employeeFirstName|employeeLastName|employeeChosenName|serverName",
                               r"^labor\.|^analytics\.(labor|check)::"),
    "wage": ("Wage", "product-management", "Restricted",
             "Hourly or job pay rate for an employee, including wage overrides. Compensation data; Restricted.",
             ["toast_payroll", "toast_payout"], r"wage|defaultWage|hourlyWage", None),
    "hours_worked": ("Hours Worked", "product-management", "Confidential",
                     "Regular, overtime and total hours recorded on time entries.",
                     ["toast_payroll"], r"regularHours|overtimeHours|totalHours", None),
    "guest_count": ("Guest Count", "product-management", "Internal",
                    "Number of guests served on an order or in a reporting period.",
                    ["location"], r"guestCount|numberOfGuests", None),
    "payout_amount": ("Payout Amount", "fintech-payments", "Confidential",
                      "Amount deposited to the restaurant's bank account for a payout period, from the Analytics payout report.",
                      ["gpv"], r"payoutAmount", None),
    "cash_entry_amount": ("Cash Entry Amount", "finance-accounting", "Confidential",
                          "Amount of a cash drawer entry or deposit recorded through Cash Management.",
                          [], r"amount", r"^cashmanagement\."),
}

# Existing business terms linked directly to identifier columns.
DIRECT_LINKS = {
    "location": (r"restaurantGuid|restaurantGUID", None),
    "customer": (r"managementGroupGuid|managementGroupGUID", None),
}


def load_columns() -> dict:
    """dataset urn -> list of field paths, from the last build of build_toast_metadata.py."""
    out = {}
    for x in json.loads((ROOT / "out" / "metadata.json").read_text(encoding="utf-8")):
        if x.get("aspectName") == "schemaMetadata":
            a = x["aspect"].get("json") or json.loads(x["aspect"]["value"])
            out[x["entityUrn"]] = [f["fieldPath"] for f in a["fields"]]
    return out


def mapping() -> dict:
    """term urn -> list of (dataset urn, field path)."""
    rules = {term_urn(k): (v[5], v[6]) for k, v in DATA_TERMS.items()}
    rules.update({term_urn(k): v for k, v in DIRECT_LINKS.items()})
    links = defaultdict(list)
    for ds, paths in load_columns().items():
        table = ds.split(",")[1]
        for p in paths:
            leaf = p.split(".")[-1]
            for t, (leaf_re, context_re) in rules.items():
                if re.fullmatch(leaf_re, leaf) and (context_re is None or re.search(context_re, f"{table}::{p}")):
                    links[t].append((ds, p))
    return links


def build_terms(domain_urn: str) -> list:
    mcps = [MetadataChangeProposalWrapper(entityUrn=NODE, aspect=GlossaryNodeInfoClass(
        name="Operational Data Terms",
        definition="Field-level business terms attached to Toast API columns. Each inherits a Classification tier and links to the KPI it feeds.",
        parentNode=ROOT_NODE))]
    for key, (name, owner, level, definition, related, _, _) in DATA_TERMS.items():
        urn = term_urn(key)
        mcps += [
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlossaryTermInfoClass(
                name=name, definition=definition, termSource="EXTERNAL",
                sourceRef="Toast Platform Guide glossary" if key in FROM_ADMIN_GLOSSARY else "Toast API documentation",
                sourceUrl=ADMIN_GLOSSARY if key in FROM_ADMIN_GLOSSARY else API_DOCS, parentNode=NODE,
                customProperties={"classification": level, "owner_functional_unit": GROUPS[owner][0],
                                  "certification_status": "Draft", "metric_type": "Data element"})),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=OwnershipClass(owners=[OwnerClass(
                owner=f"urn:li:corpGroup:{owner}", type=OwnershipTypeClass.BUSINESS_OWNER)])),
            # isRelatedTerms is DataHub's "Inherits" (IsA) relationship.
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlossaryRelatedTermsClass(
                isRelatedTerms=[tier(level)], relatedTerms=[term_urn(r) for r in related])),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=DomainsClass(domains=[domain_urn])),
        ]
    return mcps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    links = mapping()
    total = 0
    for t, cols in sorted(links.items()):
        tables = sorted({ds.split(",")[1] for ds, _ in cols})
        total += len(cols)
        print(f"{t.split(':')[-1]:<34} {len(cols):>4} columns in {len(tables):>2} tables  e.g. {cols[0][0].split(',')[1]} :: {cols[0][1]}")
    print(f"{total} column links across {len(links)} terms")

    if not args.push:
        return 0

    import os

    from datahub.emitter.rest_emitter import DatahubRestEmitter

    from dh import gql

    ds = gql("{ listDomains(input:{start:0,count:200}) { domains { urn properties { name } } } }")
    domain = next(d["urn"] for d in ds["listDomains"]["domains"] if d["properties"]["name"] == "Toast")
    emitter = DatahubRestEmitter(gms_server=os.environ["DATAHUB_GMS_URL"], token=os.environ["DATAHUB_TOKEN"])
    for m in build_terms(domain):
        emitter.emit(m)
    emitter.close()

    # One column per call: batchAddTerms with several fields of the same table in one request
    # lost about 40% of the links (concurrent writes to that table's editableSchemaMetadata).
    for t, cols in links.items():
        for ds, p in cols:
            gql("mutation($i: AddTermsInput!) { addTerms(input: $i) }", {"i": {
                "termUrns": [t], "resourceUrn": ds, "subResource": p, "subResourceType": "DATASET_FIELD"}})
    print(f"Created {len(DATA_TERMS)} operational terms and applied {total} column links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
