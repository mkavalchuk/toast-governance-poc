"""An illustrative dbt model on top of the Toast API catalog, to demonstrate lineage and KPI calculations.

    Toast API tables  ->  staging  ->  marts  ->  KPI models  ->  "Restaurant Performance KPIs" dashboard

Every model carries its SQL (View Definition tab), column-level lineage with the
transformation, glossary terms on KPI columns (GPV, Location, Net Sales, Tip...),
a Classification tier per column, owners and certification properties.

This is a teaching model, not a Toast system: the KPI formulas approximate the public
definitions in Toast's filings. Toast's internal calculations are not public.

    python scripts/lineage_model.py
"""

import json
import os
from pathlib import Path

from datahub.emitter.mce_builder import make_chart_urn, make_dashboard_urn, make_data_platform_urn, make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.mcp_builder import DatabaseKey, SchemaKey, gen_containers
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    AuditStampClass,
    BooleanTypeClass,
    BrowsePathEntryClass,
    BrowsePathsV2Class,
    ChangeAuditStampsClass,
    ChartInfoClass,
    ContainerClass,
    DashboardInfoClass,
    DataPlatformInstanceClass,
    DatasetLineageTypeClass,
    DatasetPropertiesClass,
    DateTypeClass,
    FineGrainedLineageClass,
    FineGrainedLineageDownstreamTypeClass,
    FineGrainedLineageUpstreamTypeClass,
    GlobalTagsClass,
    GlossaryTermAssociationClass,
    GlossaryTermsClass,
    NumberTypeClass,
    OtherSchemaClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StatusClass,
    StringTypeClass,
    StructuredPropertiesClass,
    StructuredPropertyValueAssignmentClass,
    SubTypesClass,
    TagAssociationClass,
    UpstreamClass,
    UpstreamLineageClass,
    ViewPropertiesClass,
)

ROOT = Path(__file__).resolve().parent.parent
DBT = "dbt"
LEVELS = ["Public", "Internal", "Confidential", "Restricted"]
ILLUSTRATIVE = "Illustrative model built for this governance demo; not a Toast production system."


def api(table):
    return make_dataset_urn("toast-api", table, "PROD")


def model(layer, name):
    return make_dataset_urn(DBT, f"toast_kpi.{layer}.{name}", "PROD")


def field_urn(ds, path):
    return f"urn:li:schemaField:({ds},{path})"


def term(key):
    return f"urn:li:glossaryTerm:toast.{key}"


TYPES = {"string": StringTypeClass, "number": NumberTypeClass, "date": DateTypeClass, "boolean": BooleanTypeClass}

P, O, R, L, M = api("orders.payments"), api("orders.orders"), api("restaurants.restaurants"), api("labor.timeEntries"), api("analytics.metrics")

# name -> (layer, description, owner group, sql, columns)
# column: (name, type, description, classification, [glossary terms], [(upstream dataset, upstream field)], transform)
MODELS = {
    "stg_payments": ("staging", "One row per payment from the Orders API, typed and renamed.", "fintech-payments", """
select
    p.guid                         as payment_guid,
    p.checkGuid                    as check_guid,
    p.orderGuid                    as order_guid,
    {{ restaurant_guid() }}        as restaurant_guid,   -- Toast-Restaurant-External-ID header of the extract
    p.paidBusinessDate::date       as business_date,
    p.type                         as payment_type,
    p.paymentStatus                as payment_status,
    p.amount                       as amount,
    p.tipAmount                    as tip_amount,
    p.cardType                     as card_type
from {{ source('toast_orders_api', 'payments') }} p""", [
        ("payment_guid", "string", "Toast GUID of the payment.", "Internal", [], [(P, "response.guid")], "IDENTITY"),
        ("check_guid", "string", "Check the payment settles.", "Internal", [], [(P, "response.checkGuid")], "IDENTITY"),
        ("order_guid", "string", "Order the check belongs to.", "Internal", [], [(P, "response.orderGuid")], "IDENTITY"),
        ("restaurant_guid", "string", "Restaurant the extract ran for, from the Toast-Restaurant-External-ID request header.", "Internal", [term("location")], [], ""),
        ("business_date", "date", "Business date the payment was made.", "Internal", [], [(P, "response.paidBusinessDate")], "CAST AS DATE"),
        ("payment_type", "string", "Tender type, for example CREDIT, CASH or GIFTCARD.", "Internal", [], [(P, "response.type")], "IDENTITY"),
        ("payment_status", "string", "Processing status, for example CAPTURED or VOIDED.", "Internal", [], [(P, "response.paymentStatus")], "IDENTITY"),
        ("amount", "number", "Payment amount before tip.", "Confidential", [term("payment_amount")], [(P, "response.amount")], "IDENTITY"),
        ("tip_amount", "number", "Tip added to the payment.", "Confidential", [term("tip")], [(P, "response.tipAmount")], "IDENTITY"),
        ("card_type", "string", "Card brand. Restricted card data; dropped in marts.", "Restricted", [term("card_data")], [(P, "response.cardType")], "IDENTITY"),
    ]),
    "stg_checks": ("staging", "One row per check from the Orders API.", "fintech-payments", """
select
    c.guid                         as check_guid,
    o.guid                         as order_guid,
    {{ restaurant_guid() }}        as restaurant_guid,
    o.businessDate                 as business_date,
    c.amount                       as check_amount,
    c.taxAmount                    as tax_amount,
    c.totalAmount                  as total_amount,
    o.numberOfGuests               as guest_count,
    c.voided                       as is_voided
from {{ source('toast_orders_api', 'orders') }} o, lateral flatten(o.checks) c""", [
        ("check_guid", "string", "Toast GUID of the check.", "Internal", [], [(O, "response.checks.guid")], "IDENTITY"),
        ("order_guid", "string", "Order the check belongs to.", "Internal", [], [(O, "response.guid")], "IDENTITY"),
        ("restaurant_guid", "string", "Restaurant the extract ran for.", "Internal", [term("location")], [], ""),
        ("business_date", "date", "Business date of the order.", "Internal", [], [(O, "response.openedDate")], "CAST AS DATE"),
        ("check_amount", "number", "Check amount before tax and tip.", "Internal", [term("check_total")], [(O, "response.checks.amount")], "IDENTITY"),
        ("tax_amount", "number", "Tax on the check.", "Internal", [], [(O, "response.checks.taxAmount")], "IDENTITY"),
        ("total_amount", "number", "Check total including tax.", "Internal", [term("check_total")], [(O, "response.checks.totalAmount")], "IDENTITY"),
        ("guest_count", "number", "Guests on the order.", "Internal", [term("guest_count")], [(O, "response.numberOfGuests")], "IDENTITY"),
        ("is_voided", "boolean", "Whether the check was voided.", "Internal", [], [(O, "response.checks.voided")], "IDENTITY"),
    ]),
    "stg_locations": ("staging", "One row per restaurant location from the Restaurants API.", "gtm-operations", """
select
    r.guid                               as restaurant_guid,
    r.general.managementGroupGuid        as management_group_guid,
    r.general.locationName               as location_name,
    r.general.timeZone                   as time_zone,
    r.general.firstBusinessDate::date    as first_business_date,
    r.general.archived                   as is_archived
from {{ source('toast_restaurants_api', 'restaurants') }} r""", [
        ("restaurant_guid", "string", "Toast GUID of the restaurant location.", "Internal", [term("location")], [(R, "response.guid"), (R, "path.restaurantGUID")], "IDENTITY"),
        ("management_group_guid", "string", "Restaurant group (customer) that owns the location.", "Internal", [term("customer")], [(R, "response.general.managementGroupGuid")], "IDENTITY"),
        ("location_name", "string", "Location display name.", "Internal", [], [(R, "response.general.locationName")], "IDENTITY"),
        ("time_zone", "string", "Location time zone.", "Internal", [], [(R, "response.general.timeZone")], "IDENTITY"),
        ("first_business_date", "date", "First business date on Toast; the go-live date.", "Internal", [], [(R, "response.general.firstBusinessDate")], "CAST AS DATE"),
        ("is_archived", "boolean", "Whether the location is archived (treated as churned).", "Internal", [], [(R, "response.general.archived")], "IDENTITY"),
    ]),
    "stg_time_entries": ("staging", "One row per employee time entry from the Labor API.", "product-management", """
select
    t.guid                       as time_entry_guid,
    t.employeeReference.guid     as employee_guid,
    t.jobReference.guid          as job_guid,
    {{ restaurant_guid() }}      as restaurant_guid,
    t.businessDate::date         as business_date,
    t.regularHours               as regular_hours,
    t.overtimeHours              as overtime_hours,
    t.hourlyWage                 as hourly_wage
from {{ source('toast_labor_api', 'timeEntries') }} t""", [
        ("time_entry_guid", "string", "Toast GUID of the time entry.", "Internal", [], [(L, "response.guid")], "IDENTITY"),
        ("employee_guid", "string", "Employee who worked the shift.", "Internal", [], [(L, "response.employeeReference")], "EXTRACT guid"),
        ("job_guid", "string", "Job the time was worked under.", "Internal", [], [(L, "response.jobReference")], "EXTRACT guid"),
        ("restaurant_guid", "string", "Restaurant the extract ran for.", "Internal", [term("location")], [], ""),
        ("business_date", "date", "Business date of the time entry.", "Internal", [], [(L, "response.businessDate")], "CAST AS DATE"),
        ("regular_hours", "number", "Regular hours worked.", "Confidential", [term("hours_worked")], [(L, "response.regularHours")], "IDENTITY"),
        ("overtime_hours", "number", "Overtime hours worked.", "Confidential", [term("hours_worked")], [(L, "response.overtimeHours")], "IDENTITY"),
        ("hourly_wage", "number", "Hourly wage for the entry. Restricted pay data.", "Restricted", [term("wage")], [(L, "response.hourlyWage")], "IDENTITY"),
    ]),
    "fct_payments": ("marts", "Captured payments with the location's processing status. Card data is dropped here.", "fintech-payments", """
select
    p.payment_guid,
    p.restaurant_guid,
    p.business_date,
    p.amount,
    p.tip_amount,
    p.payment_type = 'CREDIT'
        and l.is_toast_processing        as is_toast_processed
from {{ ref('stg_payments') }} p
join {{ ref('dim_location') }} l using (restaurant_guid)
where p.payment_status not in ('VOIDED', 'DENIED')""", [
        ("payment_guid", "string", "Payment identifier.", "Internal", [], [("stg_payments", "payment_guid")], "IDENTITY"),
        ("restaurant_guid", "string", "Location identifier.", "Internal", [term("location")], [("stg_payments", "restaurant_guid")], "IDENTITY"),
        ("business_date", "date", "Business date.", "Internal", [], [("stg_payments", "business_date")], "IDENTITY"),
        ("amount", "number", "Payment amount before tip, excluding voided and denied payments.", "Confidential", [term("payment_amount")], [("stg_payments", "amount"), ("stg_payments", "payment_status")], "FILTER status NOT IN (VOIDED, DENIED)"),
        ("tip_amount", "number", "Tip amount.", "Confidential", [term("tip")], [("stg_payments", "tip_amount")], "IDENTITY"),
        ("is_toast_processed", "boolean", "Card payment processed through Toast payments at a Toast Processing Location.", "Internal", [term("toast_processing_location")], [("stg_payments", "payment_type"), ("dim_location", "is_toast_processing")], "payment_type = 'CREDIT' AND is_toast_processing"),
    ]),
    "fct_labor_cost": ("marts", "Labor cost per time entry, with overtime at 1.5x.", "product-management", """
select
    time_entry_guid,
    restaurant_guid,
    business_date,
    regular_hours + overtime_hours                                as total_hours,
    regular_hours * hourly_wage
      + overtime_hours * hourly_wage * 1.5                        as labor_cost
from {{ ref('stg_time_entries') }}""", [
        ("time_entry_guid", "string", "Time entry identifier.", "Internal", [], [("stg_time_entries", "time_entry_guid")], "IDENTITY"),
        ("restaurant_guid", "string", "Location identifier.", "Internal", [term("location")], [("stg_time_entries", "restaurant_guid")], "IDENTITY"),
        ("business_date", "date", "Business date.", "Internal", [], [("stg_time_entries", "business_date")], "IDENTITY"),
        ("total_hours", "number", "Regular plus overtime hours.", "Confidential", [term("hours_worked")], [("stg_time_entries", "regular_hours"), ("stg_time_entries", "overtime_hours")], "regular_hours + overtime_hours"),
        ("labor_cost", "number", "Cost of the time entry. Aggregated pay; Confidential rather than Restricted.", "Confidential", [], [("stg_time_entries", "regular_hours"), ("stg_time_entries", "overtime_hours"), ("stg_time_entries", "hourly_wage")], "regular_hours * hourly_wage + overtime_hours * hourly_wage * 1.5"),
    ]),
    "dim_location": ("marts", "One row per Location with its Toast Processing status and churn flag.", "gtm-operations", """
select
    l.restaurant_guid,
    l.management_group_guid,
    l.location_name,
    l.first_business_date,
    not l.is_archived                               as is_active,
    exists (select 1 from {{ ref('stg_payments') }} p
            where p.restaurant_guid = l.restaurant_guid
              and p.payment_type = 'CREDIT')        as is_toast_processing
from {{ ref('stg_locations') }} l""", [
        ("restaurant_guid", "string", "Location identifier.", "Internal", [term("location")], [("stg_locations", "restaurant_guid")], "IDENTITY"),
        ("management_group_guid", "string", "Customer (restaurant group) identifier.", "Internal", [term("customer")], [("stg_locations", "management_group_guid")], "IDENTITY"),
        ("location_name", "string", "Location name.", "Internal", [], [("stg_locations", "location_name")], "IDENTITY"),
        ("first_business_date", "date", "Go-live date.", "Internal", [], [("stg_locations", "first_business_date")], "IDENTITY"),
        ("is_active", "boolean", "Not archived; counts toward Locations.", "Internal", [], [("stg_locations", "is_archived")], "NOT is_archived"),
        ("is_toast_processing", "boolean", "Location takes card payments through Toast; a Toast Processing Location.", "Internal", [term("toast_processing_location")], [("stg_payments", "payment_type"), ("stg_payments", "restaurant_guid")], "EXISTS credit payment at location"),
    ]),
    "kpi_gpv_daily": ("kpi", "GPV by day: dollars processed through Toast payments across Toast Processing Locations. Approximates the 10-K definition.", "fintech-payments", """
select
    business_date,
    sum(amount + tip_amount)                 as gpv,
    count(distinct restaurant_guid)          as processing_locations
from {{ ref('fct_payments') }}
where is_toast_processed
group by business_date""", [
        ("business_date", "date", "Business date.", "Internal", [], [("fct_payments", "business_date")], "GROUP BY"),
        ("gpv", "number", "Gross Payment Volume: sum of amount plus tip for Toast-processed payments.", "Confidential", [term("gpv")], [("fct_payments", "amount"), ("fct_payments", "tip_amount"), ("fct_payments", "is_toast_processed")], "SUM(amount + tip_amount) WHERE is_toast_processed"),
        ("processing_locations", "number", "Toast Processing Locations with volume that day.", "Internal", [term("toast_processing_location")], [("fct_payments", "restaurant_guid")], "COUNT(DISTINCT restaurant_guid)"),
    ]),
    "kpi_locations": ("kpi", "Location counts as of each day, split by Toast Processing status. Approximates the 10-K Locations definition.", "finance-fpa", """
select
    current_date                                              as as_of_date,
    count_if(is_active)                                       as total_locations,
    count_if(is_active and is_toast_processing)               as toast_processing_locations,
    count_if(is_active and not is_toast_processing)           as non_toast_processing_locations,
    count(distinct management_group_guid)                     as customers
from {{ ref('dim_location') }}""", [
        ("as_of_date", "date", "Measurement date.", "Internal", [], [], ""),
        ("total_locations", "number", "Active Locations (not churned).", "Internal", [term("location")], [("dim_location", "is_active"), ("dim_location", "restaurant_guid")], "COUNT_IF(is_active)"),
        ("toast_processing_locations", "number", "Active Locations using Toast payments.", "Internal", [term("toast_processing_location")], [("dim_location", "is_active"), ("dim_location", "is_toast_processing")], "COUNT_IF(is_active AND is_toast_processing)"),
        ("non_toast_processing_locations", "number", "Active Locations using Toast POS without Toast payments.", "Internal", [term("non_toast_processing_location")], [("dim_location", "is_active"), ("dim_location", "is_toast_processing")], "COUNT_IF(is_active AND NOT is_toast_processing)"),
        ("customers", "number", "Distinct restaurant groups.", "Internal", [term("customer")], [("dim_location", "management_group_guid")], "COUNT(DISTINCT management_group_guid)"),
    ]),
    "kpi_avg_check": ("kpi", "Average check size and checks per guest by location and day.", "finance-fpa", """
select
    restaurant_guid,
    business_date,
    avg(total_amount)                                as avg_check_total,
    sum(total_amount) / nullif(sum(guest_count), 0)  as spend_per_guest
from {{ ref('stg_checks') }}
where not is_voided
group by restaurant_guid, business_date""", [
        ("restaurant_guid", "string", "Location identifier.", "Internal", [term("location")], [("stg_checks", "restaurant_guid")], "GROUP BY"),
        ("business_date", "date", "Business date.", "Internal", [], [("stg_checks", "business_date")], "GROUP BY"),
        ("avg_check_total", "number", "Average check total including tax, excluding voids.", "Internal", [term("check_total")], [("stg_checks", "total_amount"), ("stg_checks", "is_voided")], "AVG(total_amount) WHERE NOT is_voided"),
        ("spend_per_guest", "number", "Check total divided by guests.", "Internal", [term("guest_count")], [("stg_checks", "total_amount"), ("stg_checks", "guest_count")], "SUM(total_amount) / SUM(guest_count)"),
    ]),
    "kpi_tip_rate": ("kpi", "Tip rate: tips as a share of payment amount, by location and day.", "fintech-payments", """
select
    restaurant_guid,
    business_date,
    sum(tip_amount) / nullif(sum(amount), 0)   as tip_rate
from {{ ref('fct_payments') }}
group by restaurant_guid, business_date""", [
        ("restaurant_guid", "string", "Location identifier.", "Internal", [term("location")], [("fct_payments", "restaurant_guid")], "GROUP BY"),
        ("business_date", "date", "Business date.", "Internal", [], [("fct_payments", "business_date")], "GROUP BY"),
        ("tip_rate", "number", "Sum of tips divided by sum of payment amounts.", "Confidential", [term("tip")], [("fct_payments", "tip_amount"), ("fct_payments", "amount")], "SUM(tip_amount) / SUM(amount)"),
    ]),
    "kpi_labor_cost_pct": ("kpi", "Labor cost as a percentage of net sales, by location and day. Joins Labor API cost to Analytics API net sales.", "finance-fpa", """
select
    m.restaurantGuid                                  as restaurant_guid,
    m.businessDate                                    as business_date,
    m.netSalesAmount                                  as net_sales,
    sum(l.labor_cost)                                 as labor_cost,
    sum(l.labor_cost) / nullif(m.netSalesAmount, 0)   as labor_cost_pct
from {{ source('toast_analytics_api', 'metrics') }} m
join {{ ref('fct_labor_cost') }} l
  on l.restaurant_guid = m.restaurantGuid and l.business_date = m.businessDate
group by 1, 2, 3""", [
        ("restaurant_guid", "string", "Location identifier.", "Internal", [term("location")], [(M, "response.restaurantGuid")], "GROUP BY"),
        ("business_date", "date", "Business date.", "Internal", [], [(M, "response.businessDate")], "GROUP BY"),
        ("net_sales", "number", "Net sales from the Analytics API.", "Confidential", [term("net_sales")], [(M, "response.netSalesAmount")], "IDENTITY"),
        ("labor_cost", "number", "Total labor cost.", "Confidential", [], [("fct_labor_cost", "labor_cost")], "SUM(labor_cost)"),
        ("labor_cost_pct", "number", "Labor cost divided by net sales.", "Confidential", [term("net_sales")], [("fct_labor_cost", "labor_cost"), (M, "response.netSalesAmount")], "SUM(labor_cost) / net_sales"),
    ]),
}

# Privacy tags on model columns, matching the tags on their Toast API sources.
COLUMN_TAGS = {
    ("stg_payments", "card_type"): ["pci"],
    ("stg_time_entries", "employee_guid"): ["pii", "pii-indirect-identifier", "data-subject-employee"],
    ("stg_time_entries", "hourly_wage"): ["compensation", "pii", "data-subject-employee"],
    ("stg_time_entries", "regular_hours"): ["pii", "data-subject-employee"],
    ("stg_time_entries", "overtime_hours"): ["pii", "data-subject-employee"],
}

CHARTS = {
    "gpv_trend": ("GPV trend", "Daily Gross Payment Volume across Toast Processing Locations.", ["kpi_gpv_daily"]),
    "location_count": ("Locations", "Active Locations split into Toast Processing and Non-Toast Processing.", ["kpi_locations"]),
    "avg_check": ("Average check and spend per guest", "Average check total and spend per guest by location.", ["kpi_avg_check"]),
    "tip_rate": ("Tip rate", "Tips as a share of payment amount.", ["kpi_tip_rate"]),
    "labor_cost_pct": ("Labor cost % of net sales", "Labor cost against net sales by location and day.", ["kpi_labor_cost_pct"]),
}
DASHBOARD = ("restaurant_performance_kpis", "Restaurant Performance KPIs",
             "Illustrative KPI dashboard built on the Toast KPI dbt model: GPV, Locations, average check, tip rate and labor cost %.")


def resolve(ref):
    """Upstream refs are either a full dataset urn or a model name in this project."""
    return ref if ref.startswith("urn:") else model(MODELS[ref][0], ref)


def build():
    stamp = AuditStampClass(time=0, actor="urn:li:corpuser:datahub")
    mcps, tables = [], []
    db = DatabaseKey(platform=DBT, env="PROD", database="toast_kpi")
    for wu in gen_containers(db, "toast_kpi", ["Project"], description="Illustrative dbt project that turns Toast API data into KPIs. " + ILLUSTRATIVE):
        mcps.append(wu.metadata)
    layers = {}
    for layer, desc in [("staging", "Typed, renamed copies of Toast API tables."),
                        ("marts", "Business facts and dimensions."),
                        ("kpi", "KPI calculations behind the Restaurant Performance dashboard.")]:
        layers[layer] = SchemaKey(platform=DBT, env="PROD", database="toast_kpi", schema=layer)
        for wu in gen_containers(layers[layer], layer, ["Schema"], parent_container_key=db, description=desc):
            mcps.append(wu.metadata)

    for name, (layer, desc, owner, sql, cols) in MODELS.items():
        urn = model(layer, name)
        top = max((c[3] for c in cols), key=LEVELS.index)
        upstream_ds = sorted({resolve(u) for c in cols for u, _ in c[5]})
        mcps += [
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=DatasetPropertiesClass(
                name=name, description=f"{desc}\n\n_{ILLUSTRATIVE}_",
                customProperties={"layer": layer, "materialization": "table" if layer != "staging" else "view",
                                  "illustrative": "true", "highest_classification": top})),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=SubTypesClass(typeNames=["Model"])),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=DataPlatformInstanceClass(platform=make_data_platform_urn(DBT))),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=ContainerClass(container=layers[layer].as_urn())),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=BrowsePathsV2Class(path=[
                BrowsePathEntryClass(id=db.as_urn(), urn=db.as_urn()),
                BrowsePathEntryClass(id=layers[layer].as_urn(), urn=layers[layer].as_urn())])),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=StatusClass(removed=False)),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=ViewPropertiesClass(
                materialized=layer != "staging", viewLogic=sql.strip(), viewLanguage="SQL")),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=SchemaMetadataClass(
                schemaName=name, platform=make_data_platform_urn(DBT), version=0, hash="",
                platformSchema=OtherSchemaClass(rawSchema=""),
                fields=[SchemaFieldClass(
                    fieldPath=c[0], type=SchemaFieldDataTypeClass(type=TYPES[c[1]]()), nativeDataType=c[1],
                    description=c[2] + (f" Calculation: `{c[6]}`." if c[6] not in ("", "IDENTITY") else ""),
                    glossaryTerms=GlossaryTermsClass(auditStamp=stamp, terms=[
                        GlossaryTermAssociationClass(urn=f"urn:li:glossaryTerm:Classification.{c[3]}"),
                        *[GlossaryTermAssociationClass(urn=t) for t in c[4]]]),
                    globalTags=GlobalTagsClass(tags=[TagAssociationClass(tag=f"urn:li:tag:{t}")
                                                     for t in COLUMN_TAGS[(name, c[0])]])
                    if (name, c[0]) in COLUMN_TAGS else None,
                ) for c in cols])),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=UpstreamLineageClass(
                upstreams=[UpstreamClass(dataset=u, type=DatasetLineageTypeClass.TRANSFORMED) for u in upstream_ds],
                fineGrainedLineages=[FineGrainedLineageClass(
                    upstreamType=FineGrainedLineageUpstreamTypeClass.FIELD_SET,
                    upstreams=[field_urn(resolve(u), f) for u, f in c[5]],
                    downstreamType=FineGrainedLineageDownstreamTypeClass.FIELD,
                    downstreams=[field_urn(urn, c[0])],
                    transformOperation=c[6] or None,
                ) for c in cols if c[5]])),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlossaryTermsClass(auditStamp=stamp, terms=[
                GlossaryTermAssociationClass(urn=f"urn:li:glossaryTerm:Classification.{top}")])),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=OwnershipClass(owners=[
                OwnerClass(owner=f"urn:li:corpGroup:{owner}", type=OwnershipTypeClass.BUSINESS_OWNER),
                OwnerClass(owner="urn:li:corpGroup:data-platform-engineering", type=OwnershipTypeClass.TECHNICAL_OWNER)])),
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=StructuredPropertiesClass(properties=[
                StructuredPropertyValueAssignmentClass(propertyUrn="urn:li:structuredProperty:toast.certificationStatus", values=["Draft"]),
                StructuredPropertyValueAssignmentClass(propertyUrn="urn:li:structuredProperty:toast.dataClassification", values=[top])])),
        ]
        tables.append({"urn": urn, "top": top})

    chart_urns = []
    for cid, (title, desc, inputs) in CHARTS.items():
        curn = make_chart_urn("looker", f"toast_kpi.{cid}")
        chart_urns.append(curn)
        mcps += [
            MetadataChangeProposalWrapper(entityUrn=curn, aspect=ChartInfoClass(
                title=title, description=f"{desc} {ILLUSTRATIVE}", lastModified=ChangeAuditStampsClass(),
                inputs=[model("kpi", i) for i in inputs])),
            MetadataChangeProposalWrapper(entityUrn=curn, aspect=OwnershipClass(owners=[
                OwnerClass(owner="urn:li:corpGroup:finance-fpa", type=OwnershipTypeClass.BUSINESS_OWNER)])),
            MetadataChangeProposalWrapper(entityUrn=curn, aspect=StatusClass(removed=False)),
        ]
    durn = make_dashboard_urn("looker", DASHBOARD[0])
    mcps += [
        MetadataChangeProposalWrapper(entityUrn=durn, aspect=DashboardInfoClass(
            title=DASHBOARD[1], description=f"{DASHBOARD[2]} {ILLUSTRATIVE}", charts=chart_urns,
            lastModified=ChangeAuditStampsClass())),
        MetadataChangeProposalWrapper(entityUrn=durn, aspect=OwnershipClass(owners=[
            OwnerClass(owner="urn:li:corpGroup:finance-fpa", type=OwnershipTypeClass.BUSINESS_OWNER)])),
        MetadataChangeProposalWrapper(entityUrn=durn, aspect=StatusClass(removed=False)),
    ]
    return mcps, tables, chart_urns + [durn], [db.as_urn()] + [k.as_urn() for k in layers.values()]


def main() -> int:
    from dh import gql

    mcps, tables, bi_assets, containers = build()
    emitter = DatahubRestEmitter(gms_server=os.environ["DATAHUB_GMS_URL"], token=os.environ["DATAHUB_TOKEN"])
    for m in mcps:
        emitter.emit(m)
    emitter.close()
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "kpi_model_tables.json").write_text(json.dumps(tables, indent=1), encoding="utf-8")

    # Finance and Metrics subdomain for everything in the model; a "Toast KPIs" data product to publish it.
    everything = [t["urn"] for t in tables] + bi_assets + containers
    gql("mutation($d: String!, $r: [ResourceRefInput!]!) { batchSetDomain(input: {domainUrn: $d, resources: $r}) }",
        {"d": "urn:li:domain:toast-finance-metrics", "r": [{"resourceUrn": u} for u in everything]})
    try:
        gql("mutation($i: CreateDataProductInput!) { createDataProduct(input: $i) { urn } }", {"i": {
            "id": "toast-kpis", "domainUrn": "urn:li:domain:toast-finance-metrics",
            "properties": {"name": "Toast KPIs", "description":
                           "Certified KPI models and dashboard (GPV, Locations, average check, tip rate, labor cost %) built from the Toast API data product. " + ILLUSTRATIVE}}})
    except RuntimeError as e:
        if "already exists" not in str(e):
            raise
    gql("mutation($p: String!, $r: [String!]!) { batchSetDataProduct(input: {dataProductUrn: $p, resourceUrns: $r}) }",
        {"p": "urn:li:dataProduct:toast-kpis", "r": [t["urn"] for t in tables] + bi_assets})
    print(f"{len(tables)} models, {len(bi_assets) - 1} charts, 1 dashboard, {len(mcps)} aspects; "
          f"domain Finance and Metrics; data product Toast KPIs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
