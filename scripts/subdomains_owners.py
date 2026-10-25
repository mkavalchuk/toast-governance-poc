"""Create business subdomains under "Toast", move each table into one, and assign owners.

Domains model accountability, so they cut across the API schemas: the Configuration API,
for example, holds menu items (Menu), tax rates (Orders and Payments) and cash drawers
(Finance and Metrics). Schemas (containers) stay in the parent Toast domain.

Ownership on every table:
  Business Owner   the functional unit that owns the subdomain
  Technical Owner  Data Platform Engineering
  Data Steward     Legal & Compliance, on tables that are Restricted or hold PII

Safe to rerun.
"""

import json
import os
import re
from pathlib import Path

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import CorpGroupInfoClass, OwnerClass, OwnershipClass, OwnershipTypeClass

from dh import gql

ROOT = Path(__file__).resolve().parent.parent

NEW_GROUPS = {
    "data-platform-engineering": ("Data Platform Engineering", "Technical owner of ingestion, catalog pipelines and the governance monitors."),
    "guest-experience": ("Guest Experience", "Owns guest-facing products and guest data, including loyalty, marketing and guest profiles."),
}

# id: (name, description, business owner group, table rules as "<schema>.<table>" regexes)
SUBDOMAINS = {
    "toast-restaurant-location": ("Restaurant and Location",
        "Restaurants, locations, restaurant groups and their operating setup such as dining options, service areas and schedules.",
        "gtm-operations",
        [r"^restaurants\.", r"^rx\.availability\.service\.", r"^ordermgmt\.configuration\.", r"^analytics\.restaurants-information$",
         r"^configuration\.(diningOptions|printers|restaurantServices|revenueCenters|serviceAreas|tables)$", r"^kitchen\.prepStations$"]),
    "toast-guest": ("Guest",
        "Guests and their personal, contact, payment card and loyalty data. Highest privacy obligations under CCPA and GDPR.",
        "guest-experience",
        [r"^analytics\.guest$"]),
    "toast-orders-payments": ("Orders and Payments",
        "Orders, checks, items sold, discounts, service charges, taxes and the payments that settle them.",
        "fintech-payments",
        [r"^orders\.", r"^creditcards\.", r"^analytics\.check$", r"^kitchen\.itemFulfillments$",
         r"^configuration\.(alternatePaymentTypes|discounts|serviceCharges|taxRates|voidReasons)$"]),
    "toast-labor-payroll": ("Labor and Payroll",
        "Employees, jobs, shifts, time entries, breaks, wages and tip withholding.",
        "product-management",
        [r"^labor\.", r"^analytics\.labor$", r"^configuration\.(breakTypes|tipWithholding)$"]),
    "toast-menu": ("Menu",
        "Menus, menu groups, items, modifiers, prices, sales categories, stock and packaging.",
        "product-management",
        [r"^menus\.", r"^menusv3\.", r"^analytics\.menu$", r"^stock\.", r"^packaging\.",
         r"^configuration\.(menuGroups|menuItems|menuOptionGroups|menus|preModifiers|preModifierGroups|priceGroups|salesCategories)$"]),
    "toast-finance-metrics": ("Finance and Metrics",
        "Sales metrics, payouts, cash management and the KPI models (ARR, GPV, Locations) built on them.",
        "finance-fpa",
        [r"^analytics\.(metrics|payout)$", r"^cashmanagement\.", r"^configuration\.(cashDrawers|noSaleReasons|payoutReasons)$",
         r"^toast_kpi\."]),
    "toast-platform-integrations": ("Platform and Integrations",
        "Authentication, partner connections and device data that integrations use to reach the Toast platform.",
        "data-platform-engineering",
        [r"^authentication\.", r"^partners\.", r"^devicedetails\."]),
}

STEWARD = "legal-compliance"
TECH = "data-platform-engineering"


def toast_domain() -> str:
    ds = gql("{ listDomains(input:{start:0,count:200}) { domains { urn properties { name } } } }")["listDomains"]["domains"]
    return next(d["urn"] for d in ds if d["properties"]["name"] == "Toast")


def subdomain_for(name: str):
    hits = [sid for sid, (_, _, _, rules) in SUBDOMAINS.items() if any(re.search(r, name) for r in rules)]
    assert len(hits) <= 1, f"{name} matches several subdomains: {hits}"
    return hits[0] if hits else None


def main() -> int:
    emitter = DatahubRestEmitter(gms_server=os.environ["DATAHUB_GMS_URL"], token=os.environ["DATAHUB_TOKEN"])
    for gid, (name, desc) in NEW_GROUPS.items():
        emitter.emit(MetadataChangeProposalWrapper(entityUrn=f"urn:li:corpGroup:{gid}",
                     aspect=CorpGroupInfoClass(displayName=name, description=desc, admins=[], members=[], groups=[])))

    parent = toast_domain()
    for sid, (name, desc, owner, _) in SUBDOMAINS.items():
        try:
            gql("mutation($i: CreateDomainInput!) { createDomain(input: $i) }",
                {"i": {"id": sid, "name": name, "description": desc, "parentDomain": parent}})
            print(f"created subdomain {name}")
        except RuntimeError as e:
            if "already exists" not in str(e):
                raise
        emitter.emit(MetadataChangeProposalWrapper(entityUrn=f"urn:li:domain:{sid}", aspect=OwnershipClass(owners=[
            OwnerClass(owner=f"urn:li:corpGroup:{owner}", type=OwnershipTypeClass.BUSINESS_OWNER)])))

    tables = json.loads((ROOT / "out" / "summary.json").read_text(encoding="utf-8"))
    extra = ROOT / "out" / "kpi_model_tables.json"  # written by lineage_model.py
    if extra.exists():
        tables += json.loads(extra.read_text(encoding="utf-8"))

    plan, unmapped = {}, []
    for t in tables:
        name = t["urn"].split(",")[1]
        sid = subdomain_for(name)
        (plan.setdefault(sid, []) if sid else unmapped).append(t)
    assert not unmapped, f"tables with no subdomain: {[t['urn'] for t in unmapped]}"

    for sid, items in plan.items():
        gql("mutation($d: String!, $r: [ResourceRefInput!]!) { batchSetDomain(input: {domainUrn: $d, resources: $r}) }",
            {"d": f"urn:li:domain:{sid}", "r": [{"resourceUrn": t["urn"]} for t in items]})
        owner = SUBDOMAINS[sid][2]
        for t in items:
            owners = [OwnerClass(owner=f"urn:li:corpGroup:{owner}", type=OwnershipTypeClass.BUSINESS_OWNER),
                      OwnerClass(owner=f"urn:li:corpGroup:{TECH}", type=OwnershipTypeClass.TECHNICAL_OWNER)]
            # Legal & Compliance stewards anything Restricted and any table holding personal data.
            if t.get("top") == "Restricted" or "pii" in t.get("tags", []):
                owners.append(OwnerClass(owner=f"urn:li:corpGroup:{STEWARD}", type=OwnershipTypeClass.DATA_STEWARD))
            emitter.emit(MetadataChangeProposalWrapper(entityUrn=t["urn"], aspect=OwnershipClass(owners=owners)))
        print(f"{SUBDOMAINS[sid][0]:<26} {len(items):>3} tables  owner: {owner}")
    emitter.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
