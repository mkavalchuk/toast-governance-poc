"""Place each Toast glossary term in the subdomain whose data it describes. Safe to rerun."""

from business_glossary import TERMS, term_urn
from dh import gql
from link_terms import DATA_TERMS

BY_SECTION = {"kpi": "toast-finance-metrics", "nongaap": "toast-finance-metrics", "revenue": "toast-finance-metrics"}
OVERRIDES = {
    # business terms
    "location": "toast-restaurant-location", "toast_processing_location": "toast-restaurant-location",
    "non_toast_processing_location": "toast-restaurant-location", "customer": "toast-restaurant-location",
    "gpv": "toast-orders-payments", "payments_arr": "toast-orders-payments",
    "toast_capital": "toast-orders-payments", "easy_pay": "toast-orders-payments", "automated_surcharging": "toast-orders-payments",
    "toast_payout": "toast-labor-payroll", "payroll_card": "toast-labor-payroll", "toast_payroll": "toast-labor-payroll",
    "xtrachef": "toast-menu", "toast_iq": "toast-platform-integrations", "toast_benchmarking": "toast-finance-metrics",
    "tps": "toast-orders-payments",
    # operational data terms
    "guest_contact_info": "toast-guest", "guest_count": "toast-restaurant-location",
    "payment_amount": "toast-orders-payments", "tip": "toast-orders-payments", "gratuity": "toast-orders-payments",
    "check_total": "toast-orders-payments", "discount_amount": "toast-orders-payments", "refund_amount": "toast-orders-payments",
    "card_data": "toast-orders-payments",
    "wage": "toast-labor-payroll", "hours_worked": "toast-labor-payroll", "employee_personal_data": "toast-labor-payroll",
    "menu_item_price": "toast-menu",
    "net_sales": "toast-finance-metrics", "gross_sales": "toast-finance-metrics", "payout_amount": "toast-finance-metrics",
    "cash_entry_amount": "toast-finance-metrics",
}

plan = {}
for key, t in TERMS.items():
    plan.setdefault(OVERRIDES.get(key) or BY_SECTION[t[0]], []).append(term_urn(key))
for key in DATA_TERMS:
    plan.setdefault(OVERRIDES[key], []).append(term_urn(key))

for sid, urns in plan.items():
    gql("mutation($d: String!, $r: [ResourceRefInput!]!) { batchSetDomain(input: {domainUrn: $d, resources: $r}) }",
        {"d": f"urn:li:domain:{sid}", "r": [{"resourceUrn": u} for u in urns]})
    print(f"{sid:<30} {len(urns):>2} terms")
