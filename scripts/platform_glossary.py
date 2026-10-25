"""Toast Platform Glossary: restaurant and POS vocabulary, linked to the tables and columns it describes.

Sources
  - Toast Platform Guide glossary (112 entries):
    https://doc.toasttab.com/doc/platformguide/adminGlossary.html
  - Object definitions in Toast's published API specifications (API Data Objects section).

Definitions are written in our own words; each term links back to its source. Where a
concept already exists in the Toast Business Glossary (Net Sales, Gross Sales, Tip,
Gratuity) it is not duplicated: the existing term is related instead, and its definition
follows Toast's reporting definition (see link_terms.py). Aliases from the source
(Closeout hour, Wheelman, Modifier option) are folded into their main term.

    python scripts/platform_glossary.py           # print the plan
    python scripts/platform_glossary.py --push    # create terms and apply table and column links
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADMIN = "https://doc.toasttab.com/doc/platformguide/adminGlossary.html"
SPECS = "https://doc.toasttab.com/openapi/"
ROOT_NODE = "urn:li:glossaryNode:toast_platform_glossary"
READING_GUIDE = "https://smart-gannet-2f4400.trials.acryl.io/document/urn:li:document:toast-reading-api-tables"
SOURCE_INFO = {  # source key: (reference, url, term kind)
    "admin": ("Toast Platform Guide glossary", ADMIN, "Platform term"),
    "api": ("Toast API specifications", SPECS, "API data object"),
    "catalog": ("How to read Toast API tables (catalog guide)", READING_GUIDE, "Catalog convention"),
}
API_TABLE_TERM = "urn:li:glossaryTerm:toast.pg.api_table"

# section: (name, description, owner group, subdomain)
SECTIONS = {
    "orders": ("Orders and Checks", "How orders and checks move from entry to close.", "product-management", "toast-orders-payments"),
    "payments": ("Payments", "Card payment lifecycle from authorization to settlement.", "fintech-payments", "toast-orders-payments"),
    "tips": ("Tips, Gratuities and Service Charges", "Charges added to a check and how they reach employees.", "fintech-payments", "toast-orders-payments"),
    "discounts": ("Discounts and Promotions", "Price reductions, comps and guest credits.", "product-management", "toast-orders-payments"),
    "cash": ("Cash Management", "Cash drawers, cash movements, deposits and reconciliation.", "finance-accounting", "toast-finance-metrics"),
    "menu": ("Menu", "How menus, items and modifiers are structured.", "product-management", "toast-menu"),
    "kitchen": ("Kitchen", "Back-of-house fulfillment, prep stations and kitchen displays.", "product-management", "toast-restaurant-location"),
    "foh": ("Front of House and Staff", "Guest-facing areas, roles and end-of-shift processes.", "product-management", "toast-labor-payroll"),
    "reporting": ("Reporting", "Business day boundaries and end-of-day reports.", "finance-fpa", "toast-finance-metrics"),
    "segments": ("Restaurant Segments and Types", "Market segments and restaurant formats Toast sells to.", "gtm-operations", "toast-restaurant-location"),
    "platform": ("Toast Platform and Hardware", "Toast software surfaces, devices and hardware support.", "product-management", "toast-platform-integrations"),
    "slang": ("Restaurant Language", "Everyday restaurant expressions used by staff.", "product-management", "toast-restaurant-location"),
    "api": ("API Data Objects", "Business objects as Toast's APIs define them; each maps to Toast API tables and fields.", "data-platform-engineering", "toast-platform-integrations"),
    "catalog": ("Catalog Conventions", "How to read the Toast API tables in this catalog, including the query., path. and response. column prefixes.",
                "data-platform-engineering", "toast-platform-integrations"),
}

# key: (name, section, definition, related term keys, links)
# links: {"tables": [...], "columns": [(leaf regex, context regex searched in "<table>::<path>" or None)],
#         "owner": override, "domain": override, "aka": alias, "source": "admin" | "api"}
T = {}


def term(key, name, section, definition, related=(), **links):
    T[key] = (name, section, definition, list(related), links)


# ---- Orders and Checks
term("open_order", "Open order", "orders", "An order that has been entered but not yet paid.", ["paid_order", "closed_order", "order"],
     columns=[(r"openedDate", r"orders\.")])
term("paid_order", "Paid order", "orders", "An order whose payment has been taken but which the server has not yet closed, typically while the tip is still being added.",
     ["open_order", "closed_order"], columns=[(r"paidDate|paidBusinessDate", r"orders\.")])
term("closed_order", "Closed order", "orders", "An order that is fully paid, including tip, and closed by the server.", ["paid_order"],
     columns=[(r"closedDate", r"orders\.")])
term("balance_due", "Balance due", "orders", "What is still owed on a check after taxes, discounts and credits; for a split check, the amount needed to close it.",
     ["check_total", "subtotal"])
term("subtotal", "Subtotal", "orders", "The check balance before credits, discounts and taxes are applied.", ["check_total", "balance_due"])
term("dining_option", "Dining option", "orders", "How an order reaches the guest, such as dine in, takeout or delivery. Kitchen displays can filter orders by it.",
     ["order"], tables=["configuration.diningOptions"], columns=[(r"diningOption|diningOptionName", None)])
term("revenue_center", "Revenue center", "orders", "A part of the front of house that generates income and can be reported on separately, such as the bar or a private dining room.",
     ["service_area", "net_sales"], tables=["configuration.revenueCenters"], columns=[(r"revenueCenter", None)], domain="toast-restaurant-location")
term("service_area", "Service area", "orders", "A physical area where guests are served, made up of tables, such as the patio or dining room.",
     ["revenue_center", "table"], tables=["configuration.serviceAreas"], columns=[(r"serviceArea", None)], domain="toast-restaurant-location")
term("seat", "Seat", "orders", "A numbered position at a table that tells servers which guest ordered which items.", ["cover", "top"],
     columns=[(r"seatNumber", None)])
term("cover", "Cover", "orders", "One guest. Cover counts are a common measure of restaurant volume.", ["guest_count", "seat"])
term("top", "Top", "orders", "The number of seats at a table, as in a four top; a two-seat table is a deuce.", ["seat", "table"])
term("turn", "Turn (turn time)", "orders", "One full cycle of a table from seating the guests through payment and resetting for the next party.", ["top"])
term("hold", "Hold", "orders", "A POS action that keeps an order on the device without sending it to the kitchen yet.", ["send", "stay"])
term("send", "Send", "orders", "A POS action that sends an order, or part of it, to the kitchen to start preparation.", ["hold", "stay", "fire"])
term("stay", "Stay", "orders", "A POS action that sends items to the kitchen while keeping the ordering screen open for more.", ["send", "hold"])
term("open_item", "Open item", "orders", "An item entered at the POS that is not on the menu, such as a corkage fee or room rental, usually with a price set at the time.",
     ["menu_item_price"], columns=[(r"openPriceAmount", None)])

# ---- Payments
term("payment_authorization", "Payment authorization", "payments", "A temporary hold for the transaction amount on the cardholder's account. It is released if not settled within seven days.",
     ["uncaptured_payment", "captured_payment"], columns=[(r"paymentStatus", r"payments")])
term("uncaptured_payment", "Uncaptured payment", "payments", "A card authorization that has not yet been captured; it can expire if not captured within seven days.",
     ["payment_authorization", "auto_capturing"])
term("captured_payment", "Captured payment", "payments", "An authorized card transaction that has been sent to the card issuer, so the guest's account is charged.",
     ["settled_payment", "payment_authorization"])
term("settled_payment", "Settled payment", "payments", "A card transaction that has been authorized, captured and deposited to the restaurant's bank account.",
     ["captured_payment", "gpv"])
term("auto_capturing", "Auto-capturing", "payments", "Toast captures any remaining uncaptured card payments at the end of the business day so they are deposited.",
     ["uncaptured_payment", "business_day_cutoff"])
term("background_payments", "Background payments", "payments", "Card payments the POS could not authorize at the time of sale, for example while offline, that are authorized later.",
     ["offline_payments"])
term("offline_payments", "Offline payments", "payments", "Payments taken while a Toast device is offline; they are authorized and processed once the connection returns.",
     ["background_payments"])
term("merchant_cash_advance", "Merchant cash advance (MCA)", "payments", "Funding from a card processor that is repaid by withholding a share of the restaurant's future card sales.",
     ["toast_capital"], columns=[(r"mcaRepaymentAmount", None)])

# ---- Tips, gratuities and service charges
term("service_charge", "Service charge", "tips", "A fee the restaurant adds to a check. It is either kept by the restaurant (and counted in net sales) or paid to employees as a gratuity.",
     ["gratuity", "net_sales"], tables=["configuration.serviceCharges"], columns=[(r"appliedServiceCharges", None)])
term("auto_gratuity", "Auto-gratuity", "tips", "The IRS name for a service charge that Toast treats as a gratuity: set by the restaurant and passed to the employee who owns the check.",
     ["gratuity", "service_charge"])
term("clawback", "Clawback (tip withholding)", "tips", "A setting that lets a restaurant keep a percentage of employees' card tips to offset card processing fees.",
     ["tip", "toast_payroll"], tables=["configuration.tipWithholding"], columns=[(r"tipsWithheld", None)], owner="legal-compliance",
     domain="toast-labor-payroll")
term("tip_out", "Tip out", "tips", "Cash the restaurant pays an employee at shift review for card tips owed to them.", ["tip", "shift_review"],
     domain="toast-labor-payroll")

# ---- Discounts and promotions
term("bogo", "BOGO", "discounts", "Buy one, get one: a promotion that reduces the price of a get item when a buy item is ordered.", ["buy_item", "get_item", "discount_amount"],
     tables=["configuration.discounts"])
term("buy_item", "Buy item", "discounts", "The item that qualifies an order for a BOGO discount.", ["bogo", "get_item"])
term("get_item", "Get item", "discounts", "The item whose price is reduced by a BOGO discount.", ["bogo", "buy_item"])
term("comp", "Comp", "discounts", "Giving an item away free, usually approved by a manager to resolve a problem or reward a guest.", ["discount_amount"])
term("customer_credit", "Customer credit", "discounts", "A credit a guest can redeem on a future visit, often given to make up for a poor experience.",
     ["discount_amount", "net_sales"], owner="guest-experience", domain="toast-guest")

# ---- Cash management
term("cash_drawer_states", "Cash drawer states", "cash", "A cash drawer is active, open or closed at any time.", ["starting_balance"],
     tables=["configuration.cashDrawers"], columns=[(r"cashDrawer", None)])
term("starting_balance", "Starting balance", "cash", "The cash placed in a drawer when it is created.", ["automatic_cash_drawer_reset", "manual_cash_drawer_reset"])
term("automatic_cash_drawer_reset", "Automatic cash drawer reset", "cash", "When a new drawer replaces a closed one, its starting balance is set to the configured amount.",
     ["starting_balance", "manual_cash_drawer_reset"])
term("manual_cash_drawer_reset", "Manual cash drawer reset", "cash", "When a new drawer replaces a closed one, the employee enters the starting balance.",
     ["starting_balance", "automatic_cash_drawer_reset"])
term("cash_in", "Cash in", "cash", "Adding cash to an active or open drawer.", ["cash_out", "cash_entry"])
term("cash_out", "Cash out", "cash", "Taking cash out of an active or open drawer.", ["cash_in", "cash_drop", "pay_out"])
term("cash_drop", "Cash drop", "cash", "Moving cash from a drawer to a safer place such as the office safe, tracked against the restaurant's cash balance and capped at the drawer balance.",
     ["cash_out", "cash_entry"])
term("pay_out", "Pay out", "cash", "Removing cash from a drawer for an expense, with a reason configured in Toast Web.", ["cash_out", "payout_reason"],
     tables=["configuration.payoutReasons"])
term("cash_in_drawer", "Cash in drawer", "cash", "Cash payments an employee placed in a drawer; reported at shift review but not owed because the restaurant already holds it.",
     ["cash_in_hand", "shift_review"])
term("cash_in_hand", "Cash in hand", "cash", "Cash payments an employee kept in their own bank during the shift and owes the restaurant at shift review.",
     ["cash_in_drawer", "cash_collected"])
term("cash_collected", "Cash collected", "cash", "Cash the restaurant collects from an employee at shift review, matching their cash in hand.", ["cash_in_hand", "shift_review"])
term("cash_drawer_lockdown", "Cash drawer lockdown", "cash", "Locking a drawer to one employee for a shift so only they can take payments into it.",
     ["blind_cash_drawer_access", "full_cash_drawer_access"], owner="legal-compliance")
term("blind_cash_drawer_access", "Blind cash drawer access", "cash", "A permission to manage cash drawers without seeing their balances, used to reduce cash risk.",
     ["full_cash_drawer_access", "cash_drawer_lockdown"], owner="legal-compliance")
term("full_cash_drawer_access", "Full cash drawer access", "cash", "A permission to manage cash drawers and see every drawer's balance.", ["blind_cash_drawer_access"], owner="legal-compliance")
term("expected_closeout_cash", "Expected closeout cash", "cash", "The drawer balance Toast calculates from cash activity such as cash payments, collections, tip payouts and drops.",
     ["actual_closeout_cash"])
term("actual_closeout_cash", "Actual closeout cash", "cash", "The drawer balance counted by hand at close and entered in Toast; compared with expected closeout cash.",
     ["expected_closeout_cash"])
term("expected_deposit", "Expected deposit", "cash", "The cash deposit Toast expects based on actual closeout balances and other cash the restaurant holds.", ["actual_deposit", "deposit"])
term("actual_deposit", "Actual deposit", "cash", "The total cash deposit entered in Toast.", ["expected_deposit", "deposit"], columns=[(r"amount", r"^cashmanagement\.deposits::")])
term("cash_drawer_history_report", "Cash drawer history report", "cash", "A report of all cash activity at one restaurant for one day.", ["cash_drawer_overview_report"])
term("cash_drawer_overview_report", "Cash drawer overview report", "cash", "A report of drawer balances, discrepancies and deposits across several restaurants for one day.",
     ["cash_drawer_history_report"])

# ---- Menu
term("menu_group", "Menu group", "menu", "A section of a menu, such as sandwiches on the lunch menu.", ["menu", "menu_item"],
     tables=["configuration.menuGroups"], columns=[(r"menuGroups|menuGroupName", None)])
term("modifier", "Modifier (modifier option)", "menu", "An option that changes a menu item when it is ordered, such as a cheese choice or cooking temperature.",
     ["modifier_group", "menu_item"], columns=[(r"modifiers|modifierName", None)], aka="Modifier option")
term("modifier_group", "Modifier group", "menu", "A set of related modifiers shown together on the ordering screen.", ["modifier"],
     tables=["configuration.menuOptionGroups"], columns=[(r"modifierGroups|modifierGroupReferences|optionGroups", None)])
term("independent_modifier", "Independent modifier", "menu", "A modifier prepared and served separately from its item, such as a side salad with a steak.", ["modifier", "integral_modifier"])
term("integral_modifier", "Integral modifier", "menu", "A modifier that is part of completing the item, such as how a burger is cooked.", ["modifier", "independent_modifier"])
term("menu_inheritance", "Inheritance", "menu", "Applying the same settings to a group of related items, such as a menu group, job or restaurant group, so its members pick them up.",
     ["menu_group"])
term("production_item", "Production item", "menu", "An ingredient or component shared by several items, tracked on the KDS so cooks know how many to prepare.",
     ["kitchen_display_system"], domain="toast-restaurant-location")
term("sku", "Stockkeeping unit (SKU)", "menu", "A code, usually alphanumeric, that identifies a product for inventory tracking.", ["menu_item"],
     tables=["stock.inventory"], columns=[(r"sku", None)])
term("eighty_six", "86", "menu", "To take an item off the menu, usually because it has run out.", ["menu_item"], tables=["stock.inventory"])

# ---- Kitchen
term("back_of_house", "Back of house (BOH)", "kitchen", "The areas guests do not see, such as the kitchen, prep and storage areas and offices, and the staff who work there.",
     ["front_of_house"])
term("prep_station", "Prep station", "kitchen", "A kitchen area where a type of food is prepared; in Toast, the KDS or printer that receives those items.",
     ["kitchen_display_system", "expediter"], tables=["kitchen.prepStations"], columns=[(r"prepStation\w*", None)])
term("no_print_prep_station", "No Print prep station", "kitchen", "A virtual prep station for items that need no kitchen work, such as retail goods, so no ticket is produced.",
     ["prep_station"])
term("non_printing_prep_station", "Non-printing prep station", "kitchen", "A device setting that stops a KDS from printing tickets for orders entered on that same device.",
     ["prep_station"])
term("kitchen_display_system", "Kitchen display system (KDS)", "kitchen", "Screens, usually wall-mounted tablets, that show orders to cooks, expediters and bartenders instead of or alongside printed tickets.",
     ["prep_station", "expediter"], tables=["kitchen.itemFulfillments"])
term("expediter", "Expediter (Expo)", "kitchen", "The person, or the KDS or printer, that coordinates finished food leaving the kitchen; also called the wheelman.",
     ["prep_station", "two_level_fulfillment"], aka="Wheelman")
term("two_level_fulfillment", "Two-level fulfillment", "kitchen", "A KDS flow where items finished at prep stations pass through two expediter screens before serving.", ["expediter"])
term("fire", "Fire", "kitchen", "To start cooking an order or part of one.", ["send"], columns=[(r"fireTime|firedDate|fireStatus", None)])
term("all_day", "All day", "kitchen", "The total count of an item still to be prepared across all open orders.", ["production_item"])
term("auction", "Auction", "kitchen", "Walking food around and asking guests who ordered it because the ticket has no clear table or seat.", ["seat"])
term("dupe", "Dupe", "kitchen", "The printed ticket the server sends to the kitchen with what to prepare and when.", ["send"])
term("rail", "Rail", "kitchen", "A fixed holder that displays printed tickets in the kitchen; a KDS can replace it.", ["kitchen_display_system"])
term("wheel", "Wheel", "kitchen", "A spinning holder for printed tickets in the kitchen; a KDS can replace it.", ["kitchen_display_system"])
term("line_cook", "Line cook", "kitchen", "A cook who works a prep station.", ["prep_station"], domain="toast-labor-payroll")

# ---- Front of house and staff
term("front_of_house", "Front of house (FOH)", "foh", "The guest-facing areas, such as the bar, dining room and waiting area, and the staff who work there.",
     ["back_of_house"], domain="toast-restaurant-location")
term("server", "Server", "foh", "The waiter or waitress responsible for a guest's check.", ["employee", "station"],
     columns=[(r"server|serverName", None)])
term("bartender", "Bartender", "foh", "The server for the bar, who fills drink orders and also serves their own guests.", ["server"])
term("busser", "Busser", "foh", "Staff who clear plates between courses and after guests leave.", ["server"])
term("host", "Host", "foh", "Staff who greet and seat guests and manage seating and reservations.", ["server"])
term("station", "Station", "foh", "A section of the floor assigned to a server or, in the kitchen, a prep station.", ["server", "prep_station"])
term("shift_review", "Shift review", "foh", "The end-of-shift process that closes checks, returns cash and pays out tips and gratuities, with a printed summary.",
     ["tip_out", "cash_in_hand", "time_entry"])
term("line_busting", "Line busting", "foh", "Taking orders with a handheld device in the middle of a line to speed service.", ["toast_pos_device"])

# ---- Reporting
term("business_day_cutoff", "Business day cutoff time (closeout hour)", "reporting",
     "The hour that ends one business day and starts the next, set between midnight and noon. Orders after midnight but before it count toward the previous business date.",
     ["business_date", "z_report"], columns=[(r"closeoutHour", None)], aka="Closeout hour")
term("z_report", "Z report (closeout report)", "reporting", "The one-day sales summary produced when a restaurant closes out the day on a Toast device.",
     ["business_day_cutoff", "net_sales"])

# ---- Segments and types
term("smb", "Small and medium-sized business (SMB)", "segments", "Restaurants with 1 to 10 locations, such as an independent restaurant.", ["mid_market", "enterprise", "customer"])
term("mid_market", "Mid market account (MM)", "segments", "Restaurants with 11 to 50 locations.", ["smb", "enterprise", "customer"])
term("enterprise", "Enterprise", "segments", "Restaurant groups with more than 50 locations, such as a chain.", ["smb", "mid_market", "customer"])
term("full_service_restaurant", "Full service restaurant (FSR)", "segments", "A restaurant with table service, from diners and bars to fine dining.",
     ["quick_service_restaurant", "fast_casual"])
term("quick_service_restaurant", "Quick service restaurant (QSR)", "segments", "A restaurant with a limited, low-cost menu served at a counter or drive-through.",
     ["fast_casual", "full_service_restaurant"])
term("fast_casual", "Fast casual", "segments", "Counter service with a limited, moderately priced menu and a more upscale feel than a QSR, such as a cafe or food truck.",
     ["quick_service_restaurant"])
term("implementation", "Implementation", "segments", "The process of getting a restaurant live on Toast.", ["location"], columns=[(r"firstBusinessDate", None)])

# ---- Platform and hardware
term("toast_platform", "Toast platform", "platform", "Toast's point of sale product: the POS app, restaurant hardware, Toast Web and related workflows.", ["toast_web", "toast_pos_device"])
term("point_of_sale", "Point of sale (POS)", "platform", "The hardware, software and support that run sales transactions, including itemization, card processing and receipts.",
     ["toast_platform"])
term("toast_web", "Toast Web", "platform", "The web-based restaurant administration site, also reachable from a POS device.", ["toast_platform"])
term("toast_pos_device", "Toast POS device", "platform", "A tablet or handheld running the Toast POS app.", ["toast_platform", "guest_facing_display"],
     tables=["devicedetails.device-info"], columns=[(r"posDeviceInfo|createdDevice|lastModifiedDevice", None)])
term("pos_home_screen", "Toast POS home screen", "platform", "The device page that gives access to features beyond the device's main mode, filtered by the user's permissions.",
     ["toast_pos_device"])
term("guest_facing_display", "Guest Facing Display (GFD)", "platform", "A screen attached to a POS device that shows the guest their items, prices and total.", ["toast_pos_device"])
term("overflow_menu", "Overflow menu", "platform", "The icon in the corner of each POS screen that lists extra options for that screen.", ["toast_pos_device"])
term("rma", "Return Merchandise Authorization (RMA)", "platform", "The first step to replace faulty Toast hardware, issued by Customer Care after troubleshooting.",
     ["toast_pos_device", "hardware_professional_services"], owner="gtm-operations")

# ---- Restaurant language
term("in_the_weeds", "In the weeds", "slang", "Very busy, more orders or guests than staff can comfortably handle.", ["all_day"])
term("on_the_fly", "On the fly", "slang", "A request to prepare something as fast as possible.", ["fire"])
term("push", "Push", "slang", "To promote a particular item, often one that needs to sell soon.", ["upsell"])
term("upsell", "Upsell", "slang", "Suggesting a higher-priced option without calling attention to the price.", ["push", "menu_item_price"])

# ---- API data objects (from Toast's API specifications)
term("guid", "GUID", "api", "The globally unique identifier Toast assigns to every platform entity; the `guid` field on Toast API objects.",
     ["external_id", "entity_type"], columns=[(r"guid", r"::response\.guid$")], source="api")
term("external_id", "External ID", "api", "An identifier supplied by a partner system, prefixed by its naming authority, that lets integrations refer to a Toast entity without its GUID.",
     ["guid"], columns=[(r"externalId", r"::response\.externalId$")], source="api")
term("entity_type", "Entity type", "api", "The kind of Toast object a reference points to, returned as `entityType`.", ["guid"],
     columns=[(r"entityType", r"::response\.entityType$")], source="api")
term("business_date", "Business date", "api", "The restaurant's operating day an activity belongs to, which can differ from the calendar date because of the business day cutoff.",
     ["business_day_cutoff"], columns=[(r"businessDate|paidBusinessDate|voidBusinessDate|refundBusinessDate", None)], source="api",
     domain="toast-finance-metrics")
term("management_group", "Management group (restaurant group)", "api", "A set of restaurants managed together, such as a chain; the customer-level grouping in Toast APIs.",
     ["customer", "location"], tables=["restaurants.groups"], columns=[(r"managementGroupGuid|managementGroupGUID", None)], source="api",
     domain="toast-restaurant-location", owner="gtm-operations")
term("restaurant", "Restaurant", "api", "A single Toast location and its configuration, identified by its restaurant GUID.", ["location", "management_group"],
     tables=["restaurants.restaurants", "partners.restaurants", "partners.connectedRestaurants", "analytics.restaurants-information"], source="api",
     domain="toast-restaurant-location", owner="gtm-operations")
term("order", "Order", "api", "A guest order made up of one or more checks.", ["check", "open_order", "dining_option"],
     tables=["orders.orders", "orders.ordersBulk"], source="api", domain="toast-orders-payments", owner="fintech-payments")
term("check", "Check", "api", "A bill within an order, holding item selections, discounts, service charges and payments.", ["order", "selection", "check_total"],
     tables=["orders.checks", "analytics.check"], columns=[(r"checks", r"::response(\.orders)?\.checks$")], source="api",
     domain="toast-orders-payments", owner="fintech-payments")
term("selection", "Selection", "api", "An item on a check, either a menu item or a modifier on one, with its quantity and price.", ["check", "menu_item", "modifier"],
     columns=[(r"selections", None)], source="api", domain="toast-orders-payments")
term("payment", "Payment", "api", "Money applied to a check, by card, cash, gift card or another tender.", ["check", "payment_amount", "captured_payment"],
     tables=["orders.payments", "creditcards.merchants"], columns=[(r"payments", r"checks\.payments$|::response\.payments$")], source="api",
     domain="toast-orders-payments", owner="fintech-payments")
term("refund", "Refund", "api", "Money returned to a guest against an earlier payment.", ["payment", "refund_amount"], columns=[(r"refund|refundDetails", None)],
     source="api", domain="toast-orders-payments", owner="fintech-payments")
term("void", "Void", "api", "Cancelling a check, item or payment before it completes, with a required void reason.", ["void_reason"],
     columns=[(r"voided|voidInfo|voidDate", None)], source="api", domain="toast-orders-payments")
term("void_reason", "Void reason", "api", "A preconfigured reason a POS user must pick when voiding.", ["void"], tables=["configuration.voidReasons"],
     source="api", domain="toast-orders-payments")
term("no_sale_reason", "No-sale reason", "api", "A preconfigured reason for opening a cash drawer without a sale.", ["cash_drawer_states"],
     tables=["configuration.noSaleReasons"], source="api", domain="toast-finance-metrics", owner="finance-accounting")
term("payout_reason", "Payout reason", "api", "A preconfigured reason for removing cash from a drawer.", ["pay_out"], tables=["configuration.payoutReasons"],
     source="api", domain="toast-finance-metrics", owner="finance-accounting")
term("cash_entry", "Cash entry", "api", "An event where an employee puts cash into or takes cash out of a drawer.", ["cash_in", "cash_out", "cash_entry_amount"],
     tables=["cashmanagement.entries"], source="api", domain="toast-finance-metrics", owner="finance-accounting")
term("deposit", "Deposit", "api", "An event where an employee takes cash from the restaurant to the bank.", ["actual_deposit", "expected_deposit"],
     tables=["cashmanagement.deposits"], source="api", domain="toast-finance-metrics", owner="finance-accounting")
term("discount", "Discount", "api", "A price reduction configured in Toast Web, applied after service charges and before tax.", ["discount_amount", "bogo"],
     tables=["configuration.discounts", "orders.applicableDiscounts"], columns=[(r"appliedDiscounts", None)], source="api", domain="toast-orders-payments")
term("tax_rate", "Tax rate", "api", "A tax configured for a restaurant and applied to items or service charges.", ["check"], tables=["configuration.taxRates"],
     columns=[(r"appliedTaxes|taxAmount", None)], source="api", domain="toast-orders-payments", owner="finance-accounting")
term("alternate_payment_type", "Alternate payment type", "api", "A tender other than card or cash that a restaurant accepts, such as a third-party voucher.", ["payment"],
     tables=["configuration.alternatePaymentTypes"], source="api", domain="toast-orders-payments", owner="fintech-payments")
term("sales_category", "Sales category", "api", "A grouping of items used to organize sales reports, which can be set at any level from a whole menu to one item.",
     ["net_sales", "menu_item"], tables=["configuration.salesCategories"], columns=[(r"salesCategory", None)], source="api", domain="toast-menu")
term("menu", "Menu", "api", "A restaurant menu and its groups, items and modifiers as published to the POS and online ordering.", ["menu_group", "menu_item"],
     tables=["menus.menus", "menusv3.menus", "configuration.menus"], source="api", domain="toast-menu")
term("menu_item", "Menu item", "api", "A product a guest can order, with its price, modifiers and sales category.", ["menu_group", "modifier", "menu_item_price"],
     tables=["configuration.menuItems"], columns=[(r"menuItems|menuItemName", None)], source="api", domain="toast-menu")
term("pre_modifier", "Pre-modifier", "api", "A word that changes how a modifier is applied, such as extra, light or no.", ["modifier"],
     tables=["configuration.preModifiers", "configuration.preModifierGroups"], source="api", domain="toast-menu")
term("price_group", "Price group", "api", "A set of items that share pricing so prices can be managed together.", ["menu_item_price"],
     tables=["configuration.priceGroups"], source="api", domain="toast-menu")
term("restaurant_service", "Restaurant service (service period)", "api", "A named period of the day, such as lunch or dinner, used for menus and reporting.", ["business_date"],
     tables=["configuration.restaurantServices", "ordermgmt.configuration.orderingSchedule"], columns=[(r"restaurantService", None)], source="api",
     domain="toast-restaurant-location")
term("table", "Table", "api", "A dining table in a service area.", ["service_area", "top", "seat"], tables=["configuration.tables"],
     columns=[(r"table", r"::response(\.orders)?\.table$")], source="api", domain="toast-restaurant-location")
term("employee", "Employee", "api", "A restaurant employee with their jobs, wages and contact details.", ["job", "employee_personal_data", "wage"],
     tables=["labor.employees"], source="api", domain="toast-labor-payroll")
term("job", "Job", "api", "A role at a restaurant, such as server or line cook, with its default wage and tip settings.", ["employee", "wage"],
     tables=["labor.jobs"], source="api", domain="toast-labor-payroll")
term("shift", "Shift", "api", "A scheduled block of work used to control clock-in and clock-out, possibly created in an outside scheduling tool.",
     ["time_entry", "employee"], tables=["labor.shifts"], source="api", domain="toast-labor-payroll")
term("time_entry", "Time entry", "api", "The time an employee actually worked or spent on break, usually one per scheduled shift.", ["shift", "hours_worked"],
     tables=["labor.timeEntries"], source="api", domain="toast-labor-payroll")
term("break_type", "Break type", "api", "A kind of employee break, such as a paid or unpaid meal break.", ["time_entry"], tables=["configuration.breakTypes"],
     columns=[(r"breaks", r"^labor\.")], source="api", domain="toast-labor-payroll")
term("delivery_info", "Delivery info", "api", "Delivery details on an order, including the guest's address and the driver; required for delivery orders.",
     ["dining_option", "guest_contact_info"], columns=[(r"deliveryInfo", None)], source="api", domain="toast-guest", owner="guest-experience")
term("curbside_pickup", "Curbside pickup info", "api", "Details that help staff recognize a guest arriving for pickup, such as a description of their car.",
     ["dining_option"], columns=[(r"curbsidePickupInfo", None)], source="api", domain="toast-guest", owner="guest-experience")
term("loyalty_account", "Loyalty account", "api", "The guest loyalty program account attached to a check.", ["customer_credit"],
     columns=[(r"appliedLoyaltyInfo", None)], source="api", domain="toast-guest", owner="guest-experience")
term("item_fulfillment", "Item fulfillment", "api", "The record of a menu item being prepared and completed at a prep station.", ["prep_station", "kitchen_display_system"],
     tables=["kitchen.itemFulfillments"], source="api", domain="toast-restaurant-location")
term("packaging_config", "Packaging configuration", "api", "How a restaurant packages takeout and delivery orders based on guest requests, such as utensils or napkins.",
     ["dining_option"], tables=["packaging.packagingConfig"], source="api", domain="toast-menu")
term("restaurant_availability", "Restaurant availability", "api", "Whether a restaurant is currently accepting online orders.", ["restaurant"],
     tables=["rx.availability.service.availability"], source="api", domain="toast-restaurant-location")
term("pos_device", "Device", "api", "A POS terminal or printer used by the Toast platform, with its model, software and network details.", ["toast_pos_device"],
     tables=["devicedetails.device-info"], source="api", domain="toast-platform-integrations")

# ---- Catalog conventions: what the column prefixes on Toast API tables mean
term("api_table", "Toast API table", "catalog",
     "A table in this catalog that represents one Toast API resource, such as employees or orders. Its columns combine what you send "
     "to the API (query. and path. columns) with what the API returns (response. columns).",
     ["response_field", "query_parameter", "path_parameter"], source="catalog")
term("response_field", "Response field", "catalog",
     "A column starting with response. holds data the Toast API returns. Dots show nesting, so response.checks.customer.email is "
     "the email on a check's customer. These are the columns that carry data, classification and privacy tags.",
     ["api_table", "query_parameter", "path_parameter"], source="catalog")
term("query_parameter", "Query parameter", "catalog",
     "A column starting with query. is an option sent with the request to filter, page or shape the result, such as a date range "
     "or a flag to include restaurant names. It is an input, not stored data.",
     ["api_table", "response_field"], columns=[(r".+", r"::query\.")], source="catalog")
term("path_parameter", "Path parameter", "catalog",
     "A column starting with path. is an identifier placed in the request URL, such as the GUID of the employee or report being "
     "requested. It usually matches a response.guid value.",
     ["api_table", "response_field", "guid"], columns=[(r".+", r"::path\.")], source="catalog")

# Admin glossary entries already covered by an existing term, or folded into another term as an alias.
COVERED = {"Net sales": "net_sales", "Gross sales": "gross_sales", "Tip": "tip", "Gratuity": "gratuity",
           "Closeout hour": "business_day_cutoff", "Wheelman": "expediter", "Modifier option": "modifier",
           "Group": "menu_group", "Inheritance": "menu_inheritance", "Kitchen display system (KDS)": "kitchen_display_system"}

# Terms from the other glossaries this one relates to; anything not listed here must be defined above.
EXISTING = {"location", "customer", "gpv", "payment_amount", "tip", "gratuity", "check_total", "net_sales", "gross_sales",
            "discount_amount", "refund_amount", "menu_item_price", "guest_contact_info", "card_data", "employee_personal_data",
            "wage", "hours_worked", "guest_count", "payout_amount", "cash_entry_amount", "toast_payroll", "toast_payout",
            "toast_capital", "toast_processing_location", "financial_technology_solutions", "hardware_professional_services",
            "subscription_services"}


def urn(key):
    return f"urn:li:glossaryTerm:toast.{key}" if key in EXISTING else f"urn:li:glossaryTerm:toast.pg.{key}"


def node(section):
    return f"urn:li:glossaryNode:toast_pg_{section}"


def table_urn(name):
    return f"urn:li:dataset:(urn:li:dataPlatform:toast-api,{name},PROD)"


def table_terms() -> dict:
    """dataset urn -> platform glossary term urns; used by build_toast_metadata.py so rebuilds keep them."""
    out = defaultdict(list)
    for key, (_, _, _, _, links) in T.items():
        for t in links.get("tables", []):
            out[table_urn(t)].append(urn(key))
    return dict(out)


def column_links() -> dict:
    from link_terms import load_columns

    rules = {urn(k): links["columns"] for k, (_, _, _, _, links) in T.items() if links.get("columns")}
    out = defaultdict(list)
    for ds, paths in load_columns().items():
        table = ds.split(",")[1]
        for p in paths:
            leaf = p.split(".")[-1]
            for t, rs in rules.items():
                if any(re.fullmatch(lr, leaf) and (cr is None or re.search(cr, f"{table}::{p}")) for lr, cr in rs):
                    out[t].append((ds, p))
    return dict(out)


def check_coverage():
    """Every entry on the source page is either defined here or covered by an existing term."""
    src = ROOT / "sources" / "adminGlossary.json"
    if not src.exists():
        return
    names = [n for n, _ in json.loads(src.read_text(encoding="utf-8"))]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    ours = {norm(v[0]) for v in T.values()} | {norm(v[4].get("aka", "")) for v in T.values()} | {norm(n) for n in COVERED}
    short = {norm(re.sub(r"\s*\(.*\)", "", v[0])) for v in T.values()}
    missing = [n for n in names if norm(n) not in ours and norm(re.sub(r"\s*\(.*\)", "", n)) not in short
               and norm(re.sub(r",.*", "", n)) not in short]
    assert not missing, f"admin glossary entries not covered: {missing}"
    print(f"Coverage check: all {len(names)} admin glossary entries are defined or mapped")


def build(domains_ok=True):
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import (DomainsClass, GlossaryNodeInfoClass, GlossaryRelatedTermsClass,
                                                 GlossaryTermInfoClass, OwnerClass, OwnershipClass, OwnershipTypeClass)
    from business_glossary import GROUPS

    unknown = {r for v in T.values() for r in v[3]} - set(T) - EXISTING
    assert not unknown, f"related terms not defined: {unknown}"

    mcps = [MetadataChangeProposalWrapper(entityUrn=ROOT_NODE, aspect=GlossaryNodeInfoClass(
        name="Toast Platform Glossary",
        definition="Restaurant and Toast POS vocabulary from the Toast Platform Guide glossary and Toast's API object definitions, "
                   "linked to the tables and columns it describes. Definitions are paraphrased; see each term's source link.")),
            MetadataChangeProposalWrapper(entityUrn=ROOT_NODE, aspect=OwnershipClass(owners=[
                OwnerClass(owner="urn:li:corpGroup:data-platform-engineering", type=OwnershipTypeClass.BUSINESS_OWNER),
                OwnerClass(owner="urn:li:corpGroup:product-management", type=OwnershipTypeClass.BUSINESS_OWNER)]))]
    for sid, (name, desc, owner, _) in SECTIONS.items():
        mcps.append(MetadataChangeProposalWrapper(entityUrn=node(sid), aspect=GlossaryNodeInfoClass(
            name=name, definition=desc, parentNode=ROOT_NODE)))
        mcps.append(MetadataChangeProposalWrapper(entityUrn=node(sid), aspect=OwnershipClass(owners=[
            OwnerClass(owner=f"urn:li:corpGroup:{owner}", type=OwnershipTypeClass.BUSINESS_OWNER)])))
    for key, (name, section, definition, related, links) in T.items():
        _, _, owner, domain = SECTIONS[section]
        owner, domain = links.get("owner", owner), links.get("domain", domain)
        source_ref, source_url, kind = SOURCE_INFO[links.get("source", "admin")]
        props = {"owner_functional_unit": GROUPS.get(owner, (owner,))[0] if owner in GROUPS else owner,
                 "certification_status": "Draft", "metric_type": kind, "source": source_ref}
        if links.get("aka"):
            props["also_known_as"] = links["aka"]
        if links.get("tables"):
            props["tables"] = ", ".join(links["tables"])
        mcps += [
            MetadataChangeProposalWrapper(entityUrn=urn(key), aspect=GlossaryTermInfoClass(
                name=name, definition=definition, termSource="EXTERNAL" if links.get("source") != "catalog" else "INTERNAL",
                sourceRef=source_ref, sourceUrl=source_url, parentNode=node(section), customProperties=props)),
            MetadataChangeProposalWrapper(entityUrn=urn(key), aspect=OwnershipClass(owners=[
                OwnerClass(owner=f"urn:li:corpGroup:{owner}", type=OwnershipTypeClass.BUSINESS_OWNER)])),
            MetadataChangeProposalWrapper(entityUrn=urn(key), aspect=DomainsClass(domains=[f"urn:li:domain:{domain}"])),
        ]
        if related:
            mcps.append(MetadataChangeProposalWrapper(entityUrn=urn(key), aspect=GlossaryRelatedTermsClass(
                relatedTerms=[urn(r) for r in related])))
    return mcps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()

    check_coverage()
    mcps = build()
    tterms, cols = table_terms(), column_links()
    by_section = defaultdict(int)
    for v in T.values():
        by_section[SECTIONS[v[1]][0]] += 1
    for s, n in by_section.items():
        print(f"  {s:<40} {n:>3} terms")
    print(f"{len(T)} terms; {sum(len(v) for v in tterms.values())} table links on {len(tterms)} tables; "
          f"{sum(len(v) for v in cols.values())} column links from {len(cols)} terms")
    if not args.push:
        return 0

    import os

    from datahub.emitter.rest_emitter import DatahubRestEmitter

    from dh import gql

    emitter = DatahubRestEmitter(gms_server=os.environ["DATAHUB_GMS_URL"], token=os.environ["DATAHUB_TOKEN"])
    for m in mcps:
        emitter.emit(m)
    emitter.close()
    for ds, terms in tterms.items():
        gql("mutation($i: AddTermsInput!) { addTerms(input: $i) }", {"i": {"termUrns": terms, "resourceUrn": ds}})
    # One column per call: batched writes to the same table's editable schema lose updates.
    for t, pairs in cols.items():
        for ds, p in pairs:
            gql("mutation($i: AddTermsInput!) { addTerms(input: $i) }", {"i": {
                "termUrns": [t], "resourceUrn": ds, "subResource": p, "subResourceType": "DATASET_FIELD"}})
    print("Pushed terms and applied table and column links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
