"""Create the Toast Business Glossary (KPIs and business terms from public filings) in DataHub.

Every term gets a definition paraphrased from Toast's SEC filings, a business owner
group by functional unit, source links, related terms and the "Toast" domain.
Safe to rerun: all writes are upserts.

    python scripts/business_glossary.py           # write out/business_glossary.json only
    python scripts/business_glossary.py --push    # also send to DataHub
"""

import argparse
import json
from pathlib import Path

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.metadata.schema_classes import (
    CorpGroupInfoClass,
    DomainsClass,
    GlossaryNodeInfoClass,
    GlossaryRelatedTermsClass,
    GlossaryTermInfoClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
)

ROOT = Path(__file__).resolve().parent.parent

TEN_K = "https://www.sec.gov/Archives/edgar/data/1650164/000165016426000057/tost-20251231.htm"
S_1 = "https://www.sec.gov/Archives/edgar/data/1650164/000119312521258447/d166297ds1.htm"
Q2_26 = "https://www.sec.gov/Archives/edgar/data/0001650164/000165016426000162/tost-20260630xexhibit991.htm"
SOURCES = {TEN_K: "Form 10-K, fiscal year 2025", S_1: "Form S-1 (IPO registration), 2021", Q2_26: "Q2 2026 earnings release (8-K Exhibit 99.1)"}

GROUPS = {
    "finance-fpa": ("Finance - FP&A", "Owns operating KPI definitions, targets and reporting cadence (ARR, Locations, retention, unit economics)."),
    "finance-accounting": ("Finance - Accounting & SEC Reporting", "Owns revenue recognition policy, GAAP to non-GAAP reconciliations and SEC disclosure definitions."),
    "fintech-payments": ("Fintech & Payments", "Owns payment processing, GPV and financial products such as Toast Capital, PayOut and the payroll card."),
    "gtm-operations": ("Go-to-Market Operations", "Owns sales and marketing efficiency metrics, customer segmentation and location onboarding (go-live)."),
    "product-management": ("Product Management", "Owns product line definitions for the Toast platform, including software, AI and back-office offerings."),
    "legal-compliance": ("Legal & Compliance", "Owns regulated entity definitions, licensing and compliance-driven program rules."),
}

ROOT_NODE = "urn:li:glossaryNode:toast_business_glossary"
NODES = {
    "kpi": ("Key Business Metrics", "Operating metrics Toast reports to investors to show the scale and growth of the platform."),
    "nongaap": ("Non-GAAP Financial Measures", "Profitability and cash measures Toast reports alongside GAAP results, with reconciliations in each earnings release."),
    "revenue": ("Revenue Streams", "The three revenue categories Toast reports in its financial statements."),
    "products": ("Products and Programs", "Named Toast offerings that create, move or report business data."),
    "entities": ("Business Entities", "The core business objects that Toast metrics count or aggregate."),
}

# key: (node, name, owner group, definition, sources, extra properties, related term keys)
TERMS = {
    "arr": ("kpi", "ARR (Annualized Recurring Run-Rate)", "finance-fpa",
            "Operational measure of the scale of Toast's subscription and payments business. It is twelve times the subscription "
            "component of MRR plus four times the trailing three months of the payments component of MRR. It is not a GAAP "
            "measure and not a forecast of future revenue.",
            [TEN_K, Q2_26, S_1], {"metric_type": "KPI", "unit": "USD", "latest_reported_value": "$2,409M as of 2026-06-30 (+25% YoY)"},
            ["mrr", "payments_arr", "subscription_arr"]),
    "mrr": ("kpi", "MRR (Monthly Recurring Run-Rate)", "finance-fpa",
            "Measured on the last day of each month for all live Locations. The sum of subscription fees billed in the month and "
            "in-month payments fees after estimated transaction-based costs. Excludes Toast Capital fees and costs, and is not "
            "reduced by SaaS credits.",
            [TEN_K, S_1], {"metric_type": "KPI input", "unit": "USD"}, ["arr", "toast_capital"]),
    "payments_arr": ("kpi", "Payments ARR", "fintech-payments",
                     "The payments part of ARR: four times the trailing three months of the payments component of MRR.",
                     [Q2_26], {"metric_type": "KPI component", "unit": "USD", "latest_reported_value": "$1,199M as of 2026-06-30"},
                     ["arr", "gpv"]),
    "subscription_arr": ("kpi", "Subscription ARR", "finance-fpa",
                         "The subscription part of ARR: twelve times the subscription component of MRR.",
                         [Q2_26], {"metric_type": "KPI component", "unit": "USD", "latest_reported_value": "$1,210M as of 2026-06-30"},
                         ["arr", "subscription_services"]),
    "gpv": ("kpi", "GPV (Gross Payment Volume)", "fintech-payments",
            "Total dollars processed through the Toast payments platform across Toast Processing Locations in a period. Toast "
            "treats it as a key measure of platform scale; higher GPV generally means higher financial technology solutions revenue.",
            [TEN_K, Q2_26, S_1], {"metric_type": "KPI", "unit": "USD", "latest_reported_value": "$60.7B in Q2 2026 (+22% YoY)"},
            ["toast_processing_location", "financial_technology_solutions"]),
    "location": ("kpi", "Location", "finance-fpa",
                 "A unique restaurant site that has recorded transactions on Toast POS above a minimum threshold and has not been "
                 "marked as churned at the measurement date. Customers of acquired legacy products that do not use Toast POS are excluded.",
                 [TEN_K, Q2_26], {"metric_type": "KPI", "unit": "count", "latest_reported_value": "~180,000 as of 2026-06-30 (+22% YoY)"},
                 ["toast_processing_location", "non_toast_processing_location", "customer"]),
    "toast_processing_location": ("kpi", "Toast Processing Location", "fintech-payments",
                                  "A Location that also uses Toast payment processing. GPV is measured across these Locations only.",
                                  [TEN_K], {"metric_type": "KPI segment", "unit": "count"}, ["location", "gpv"]),
    "non_toast_processing_location": ("kpi", "Non-Toast Processing Location", "gtm-operations",
                                      "A Location, typically at a select enterprise customer, that uses Toast POS but not Toast payments.",
                                      [TEN_K], {"metric_type": "KPI segment", "unit": "count"}, ["location"]),
    "nrr": ("kpi", "Net Retention Rate (NRR)", "finance-fpa",
            "Customer-level retention of recurring revenue. Take the customers with at least one Location live for an entire base "
            "month and divide their MRR one year later by their MRR in the base month; churn and contraction count, new customers "
            "do not. Annual NRR is the weighted average of the trailing twelve monthly rates.",
            [S_1], {"metric_type": "KPI (IPO disclosure)", "unit": "percent", "latest_reported_value": "Above 110% each year 2015 to 2020 (S-1)"},
            ["mrr", "customer"]),
    "cac": ("kpi", "CAC (Customer Acquisition Cost)", "gtm-operations",
            "Calculated per monthly cohort of new Locations and upsells that go live: the cohort's in-month hardware and professional "
            "services gross profit (usually negative) plus sales and marketing expense from two months earlier, which is the median "
            "time from signing to go-live. Excludes stock-based compensation.",
            [S_1], {"metric_type": "Unit economics", "unit": "USD"}, ["cac_payback", "hardware_professional_services"]),
    "cac_payback": ("kpi", "CAC Payback Period", "gtm-operations",
                    "Time for a go-live cohort's estimated contribution profit to repay its CAC. Contribution profit is subscription MRR "
                    "less estimated servicing cost, plus the average payments MRR from each Location's first three full live months "
                    "less estimated payments support cost.",
                    [S_1], {"metric_type": "Unit economics", "unit": "months"}, ["cac", "mrr"]),
    "adjusted_ebitda": ("nongaap", "Adjusted EBITDA", "finance-accounting",
                        "Net income excluding stock-based compensation and related payroll tax, depreciation and amortization, net "
                        "interest income, income taxes, and certain non-operating or one-time items such as restructuring, acquisition "
                        "expenses, warrant fair value changes, early lease termination costs and stock-based charitable contributions.",
                        [Q2_26, TEN_K], {"metric_type": "Non-GAAP", "unit": "USD", "gaap_comparable": "Net income",
                                         "latest_reported_value": "$221M in Q2 2026 (includes ~$10M one-time tariff refund)"},
                        []),
    "free_cash_flow": ("nongaap", "Free Cash Flow", "finance-accounting",
                       "Net cash provided by operating activities minus purchases of property and equipment and capitalized "
                       "internal-use software.",
                       [Q2_26, TEN_K], {"metric_type": "Non-GAAP", "unit": "USD", "gaap_comparable": "Net cash provided by operating activities",
                                        "latest_reported_value": "$130M in Q2 2026"},
                       []),
    "recurring_gross_profit": ("nongaap", "Recurring Gross Profit", "finance-accounting",
                               "Non-GAAP gross profit of subscription services and financial technology solutions combined, excluding "
                               "stock-based compensation and related payroll tax and depreciation and amortization. Toast calls these its "
                               "recurring gross profit streams and guides to this measure.",
                               [Q2_26], {"metric_type": "Non-GAAP", "unit": "USD",
                                         "formal_name": "Non-GAAP subscription services and financial technology solutions gross profit",
                                         "latest_reported_value": "$595M in Q2 2026 (+28% YoY)"},
                               ["subscription_services", "financial_technology_solutions"]),
    "nongaap_gross_profit": ("nongaap", "Non-GAAP Gross Profit", "finance-accounting",
                             "Total gross profit excluding stock-based compensation and related payroll tax and depreciation and amortization.",
                             [Q2_26], {"metric_type": "Non-GAAP", "unit": "USD", "gaap_comparable": "Gross profit"},
                             ["recurring_gross_profit"]),
    "non_payments_fintech_gp": ("nongaap", "Non-Payments Fintech Gross Profit", "fintech-payments",
                                "Non-GAAP financial technology solutions gross profit minus the gross profit from payments, isolating "
                                "products such as Toast Capital and payroll money movement.",
                                [Q2_26], {"metric_type": "Non-GAAP", "unit": "USD"},
                                ["financial_technology_solutions", "toast_capital"]),
    "nongaap_opex": ("nongaap", "Non-GAAP Operating Expenses", "finance-accounting",
                     "Sales and marketing, research and development, and general and administrative expenses excluding stock-based "
                     "compensation and related payroll tax and depreciation and amortization. G&A also excludes acquisition expenses, "
                     "early lease termination costs and stock-based charitable contributions.",
                     [Q2_26], {"metric_type": "Non-GAAP", "unit": "USD"}, []),
    "subscription_services": ("revenue", "Subscription Services Revenue", "finance-accounting",
                              "Fees for access to Toast software, usually on 12 to 36 month contracts and priced mainly per Location based "
                              "on products purchased, hardware configuration and employee count.",
                              [TEN_K], {"metric_type": "Revenue stream", "latest_reported_value": "$290M in Q2 2026"},
                              ["subscription_arr", "recurring_gross_profit"]),
    "financial_technology_solutions": ("revenue", "Financial Technology Solutions Revenue", "finance-accounting",
                                       "Payment processing fees, usually a percentage of the transaction plus a per-transaction fee, "
                                       "recognized on a gross basis. Also includes fees for marketing and servicing Toast Capital loans "
                                       "originated by a bank partner.",
                                       [TEN_K], {"metric_type": "Revenue stream", "latest_reported_value": "$1,570M in Q2 2026"},
                                       ["gpv", "payments_arr", "toast_capital"]),
    "hardware_professional_services": ("revenue", "Hardware and Professional Services Revenue", "finance-accounting",
                                       "Sales of terminals, tablets, handhelds and accessories, net of expected returns, plus paid "
                                       "installation, configuration, process mapping and training services.",
                                       [TEN_K], {"metric_type": "Revenue stream", "latest_reported_value": "$48M in Q2 2026"},
                                       ["cac"]),
    "toast_capital": ("products", "Toast Capital", "fintech-payments",
                      "Working capital loans issued by a bank partner and marketed and serviced by Toast, generally repaid through a "
                      "share of the restaurant's daily card sales.",
                      [TEN_K], {"metric_type": "Product"}, ["financial_technology_solutions", "mrr"]),
    "toast_payout": ("products", "Toast PayOut", "fintech-payments",
                     "Lets restaurant employees access part of their earned wages and tips before payday, structured as a commercial "
                     "line of credit to the restaurant.",
                     [TEN_K], {"metric_type": "Product", "data_sensitivity": "Employee pay data (Restricted)"}, ["toast_payroll"]),
    "payroll_card": ("products", "Payroll Card", "fintech-payments",
                     "A debit card offered with a bank partner that lets employees receive wages, tips and other pay.",
                     [TEN_K], {"metric_type": "Product", "data_sensitivity": "Employee pay data (Restricted)"}, ["toast_payroll"]),
    "toast_payroll": ("products", "Toast Payroll and Team Management", "product-management",
                      "Payroll, tax money movement and team tools such as shift scheduling and swapping.",
                      [TEN_K], {"metric_type": "Product", "related_api": "Labor API"}, ["toast_payout", "payroll_card"]),
    "easy_pay": ("products", "Easy Pay", "fintech-payments",
                 "A commercial lease that lowers upfront hardware cost, generally repaid from a portion of daily transactions.",
                 [TEN_K], {"metric_type": "Program"}, ["hardware_professional_services"]),
    "automated_surcharging": ("products", "Automated Surcharging", "legal-compliance",
                              "Compliant credit card surcharging that helps eligible restaurants offset card processing fees, subject to "
                              "card network and state rules.",
                              [TEN_K], {"metric_type": "Program"}, ["gpv"]),
    "xtrachef": ("products", "xtraCHEF by Toast", "product-management",
                 "Back-office tools for accounts payable automation, inventory, ingredient price tracking and recipe costing.",
                 [TEN_K], {"metric_type": "Product"}, []),
    "toast_iq": ("products", "Toast IQ", "product-management",
                 "A conversational AI assistant that uses a restaurant's own operating data to surface insights and take actions in the platform.",
                 [TEN_K], {"metric_type": "Product", "data_sensitivity": "Uses customer operating data"}, []),
    "toast_benchmarking": ("products", "Toast Benchmarking", "product-management",
                           "Compares a Location's performance with aggregated data from nearby restaurants.",
                           [TEN_K], {"metric_type": "Product", "data_sensitivity": "Aggregated cross-customer data"}, ["location"]),
    "customer": ("entities", "Customer", "gtm-operations",
                 "A restaurant or food and beverage retailer using the Toast platform, from small and mid-sized operators to "
                 "multi-location and enterprise groups. A customer can own many Locations.",
                 [TEN_K, S_1], {"metric_type": "Entity", "related_api": "Restaurants API, Partners API"}, ["location", "nrr"]),
    "tps": ("entities", "Toast Processing Services LLC", "legal-compliance",
            "Toast subsidiary registered with FinCEN as a money transmitter and licensed in most states for certain payroll processing services.",
            [TEN_K], {"metric_type": "Regulated entity"}, ["toast_payroll", "financial_technology_solutions"]),
}


def term_urn(key: str) -> str:
    return f"urn:li:glossaryTerm:toast.{key}"


def build(domain_urn: str = None) -> list:
    mcps = []
    for gid, (name, desc) in GROUPS.items():
        mcps.append(MetadataChangeProposalWrapper(
            entityUrn=f"urn:li:corpGroup:{gid}",
            aspect=CorpGroupInfoClass(displayName=name, description=desc, admins=[], members=[], groups=[]),
        ))
    mcps.append(MetadataChangeProposalWrapper(entityUrn=ROOT_NODE, aspect=GlossaryNodeInfoClass(
        name="Toast Business Glossary",
        definition="Business terms and KPIs defined in Toast's public SEC filings and earnings materials, each with an owning functional unit.",
    )))
    for nid, (name, desc) in NODES.items():
        mcps.append(MetadataChangeProposalWrapper(entityUrn=f"urn:li:glossaryNode:toast_{nid}", aspect=GlossaryNodeInfoClass(
            name=name, definition=desc, parentNode=ROOT_NODE)))

    for key, (node, name, owner, definition, sources, props, related) in TERMS.items():
        urn = term_urn(key)
        props = {
            **props,
            "owner_functional_unit": GROUPS[owner][0],
            "sources": "; ".join(SOURCES[s] for s in sources),
            "certification_status": "Draft",
        }
        mcps += [
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlossaryTermInfoClass(
                name=name, definition=definition, termSource="EXTERNAL", sourceRef=SOURCES[sources[0]],
                sourceUrl=sources[0], parentNode=f"urn:li:glossaryNode:toast_{node}", customProperties=props)),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=OwnershipClass(owners=[OwnerClass(
                owner=f"urn:li:corpGroup:{owner}", type=OwnershipTypeClass.BUSINESS_OWNER)])),
        ]
        if related:
            mcps.append(MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlossaryRelatedTermsClass(
                relatedTerms=[term_urn(r) for r in related])))
        if domain_urn:
            mcps.append(MetadataChangeProposalWrapper(entityUrn=urn, aspect=DomainsClass(domains=[domain_urn])))
    return mcps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    unknown = {r for t in TERMS.values() for r in t[6]} - set(TERMS)
    assert not unknown, f"related terms not defined: {unknown}"

    domain = None
    if args.push:
        from dh import gql
        ds = gql("{ listDomains(input:{start:0,count:200}) { domains { urn properties { name } } } }")
        domain = next(d["urn"] for d in ds["listDomains"]["domains"] if d["properties"]["name"] == "Toast")

    mcps = build(domain)
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "business_glossary.json").write_text(json.dumps([m.to_obj() for m in mcps], indent=1), encoding="utf-8")
    print(f"{len(GROUPS)} owner groups, {len(NODES)} glossary sections, {len(TERMS)} terms, {len(mcps)} aspects")

    if args.push:
        import os
        from datahub.emitter.rest_emitter import DatahubRestEmitter

        emitter = DatahubRestEmitter(gms_server=os.environ["DATAHUB_GMS_URL"], token=os.environ["DATAHUB_TOKEN"])
        for m in mcps:
            emitter.emit(m)
        emitter.close()
        print(f"Pushed {len(mcps)} aspects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
