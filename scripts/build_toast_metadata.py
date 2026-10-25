"""Turn Toast's public API specs into a browsable DataHub hierarchy.

    Toast API (platform)
      Labor (schema container)          one per API spec
        employees (table dataset)       one per top-level resource
          query.* / path.* / response.* columns

Every column gets a description (from the spec, or a generated suggestion
prefixed "Suggested:"), a sample value (from the spec's example, or a synthetic
placeholder; Restricted columns are always masked) and a classification term
from the Classification glossary (Public, Internal, Confidential, Restricted).

Usage:
    python scripts/build_toast_metadata.py            # build and write out/metadata.json only
    python scripts/build_toast_metadata.py --push     # also send to DataHub

--push reads DATAHUB_GMS_URL and DATAHUB_TOKEN from the environment or from a
.env file in the repo root. The token is never printed.
"""

import argparse
import copy
import json
import os
import re
import sys
import time
import uuid
from collections import Counter, OrderedDict
from pathlib import Path

import yaml
from datahub.emitter.mce_builder import make_data_platform_urn, make_dataset_urn
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.mcp_builder import ContainerKey, gen_containers
from datahub.metadata.schema_classes import (
    ArrayTypeClass,
    AuditStampClass,
    BooleanTypeClass,
    BrowsePathEntryClass,
    BrowsePathsV2Class,
    ContainerClass,
    DataPlatformInfoClass,
    DataPlatformInstanceClass,
    DatasetFieldProfileClass,
    DatasetProfileClass,
    DatasetPropertiesClass,
    DateTypeClass,
    EnumTypeClass,
    GlossaryNodeInfoClass,
    GlossaryTermAssociationClass,
    GlossaryTermInfoClass,
    GlossaryTermsClass,
    GlobalTagsClass,
    NumberTypeClass,
    OtherSchemaClass,
    RecordTypeClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StatusClass,
    StringTypeClass,
    SubTypesClass,
    TagAssociationClass,
    TagPropertiesClass,
    TimeTypeClass,
)

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
OUT = ROOT / "out"

PLATFORM = "toast-api"
PLATFORM_URN = make_data_platform_urn(PLATFORM)
DOCS = "https://doc.toasttab.com/openapi/{slug}/overview/"

# spec file -> (schema display name, docs slug)
APIS = OrderedDict(
    [
        ("toast-reporting-api.yaml", ("Analytics", "analytics")),
        ("toast-authentication-api.yaml", ("Authentication", "authentication")),
        ("toast-cashmgmt-api.yaml", ("Cash Management", "cashmanagement")),
        ("toast-config-api.yaml", ("Configuration", "configuration")),
        ("toast-ccpartner-api.yaml", ("Credit Cards", "creditcards")),
        ("device-details-api.yaml", ("Device Details", "devicedetails")),
        ("toast-kitchen-api-docs.yaml", ("Kitchen", "kitchen")),
        ("toast-labor-api.yaml", ("Labor", "labor")),
        ("toast-menus-api.yaml", ("Menus V2", "menus")),
        ("toast-menus-api-v3.yaml", ("Menus V3", "menusv3")),
        ("toast-ordermgmt-config-api-docs.yaml", ("Order Management Configuration", "ordermgmt.configuration")),
        ("toast-orders-api.yaml", ("Orders", "orders")),
        ("packaging-api.yaml", ("Packaging Configuration", "packaging")),
        ("toast-partners-api.yaml", ("Partners", "partners")),
        ("toast-restaurant-availability-api-docs.yaml", ("Restaurant Availability", "rx.availability.service")),
        ("toast-restaurants-api.yaml", ("Restaurants", "restaurants")),
        ("toast-stock-api.yaml", ("Stock", "stock")),
    ]
)

try:
    from platform_glossary import API_TABLE_TERM, table_terms

    TABLE_TERMS = table_terms()
except ImportError:  # running from a copy without the glossary module
    TABLE_TERMS, API_TABLE_TERM = {}, None

COLUMN_GUIDE = (
    "**Reading the columns:** `response.` columns are data the API returns (dots show nesting). "
    "`query.` columns are request options such as filters or flags, and `path.` columns are IDs placed in the request URL; "
    "both are inputs, not stored data. See the glossary terms *Response field*, *Query parameter* and *Path parameter*."
)


class ToastApiKey(ContainerKey):
    api: str


SKIP_SEGMENTS ={"v1", "v2", "v3", "published", "export"}
MAX_DEPTH = 6
HTTP_METHODS = ("get", "post", "put", "patch", "delete")

# ---------------------------------------------------------------- classification

CLASSIFICATION_NODE = "urn:li:glossaryNode:Classification"
LEVELS = ["Public", "Internal", "Confidential", "Restricted"]
LEVEL_RULES = {
    "Public": "Approved for public release. No handling restrictions beyond accuracy.",
    "Internal": "For Toast employees and authorized partners only. Do not publish externally.",
    "Confidential": "Business or personal data whose exposure would harm Toast, a restaurant or a person. "
    "Share on a need-to-know basis and never in logs or analytics extracts without approval.",
    "Restricted": "Regulated or highly sensitive data such as payment card data, credentials, contact "
    "details or pay. Encrypt, mask in non-production and limit access to named roles.",
}


def term_urn(level: str) -> str:
    return f"urn:li:glossaryTerm:Classification.{level}"


# Rules are checked top to bottom. Patterns match the column's leaf name, lower-cased.
NOT_SENSITIVE = re.compile(r"pagetoken$")  # pagination cursors, not credentials
RESTRICTED = re.compile(
    r"(password|secret|token$|cardnumber|^pan$|cvv|last4|lastfour|cardholder|"
    r"expmonth|expyear|bankaccount|routingnumber|ssn|socialsecurity|taxid|"
    r"email|phone|wage|salary|payrate|passcode|^pin$|dateofbirth|birth)"
)
CONFIDENTIAL = re.compile(
    r"(firstname|lastname|chosenname|fullname|guestdisplayname|address|street|zipcode|postal|"
    r"customer|loyalty|tip|gratuity|cardtype|^employee\d?$|employeereference|deliveryemployee|"
    r"(amount|total|subtotal|cost|pay|tendered)$|^cash$|^refund(details|transaction)?$)"
)
PUBLIC_CONTEXT = re.compile(r"(menu|item|modifier|option|group|dining|availability|image|packaging|prepstation)")
PUBLIC_LEAF = re.compile(r"(^name$|description|price|image|calories|visibility|imageurl|kitchenname|posname)")


def classify(table: str, path: str) -> str:
    parts = path.split(".")
    leaf = parts[-1].lower()
    context = ".".join(parts[:-1]).lower() + "." + table.lower()
    if NOT_SENSITIVE.search(leaf):
        return "Internal"
    if RESTRICTED.search(leaf):
        return "Restricted"
    # Menu content (item names, descriptions, prices) is what guests see on a menu.
    if PUBLIC_CONTEXT.search(context) and PUBLIC_LEAF.search(leaf):
        return "Public"
    if leaf == "name" and not re.search(r"(customer|guest|employee|server|user|person)", context):
        return "Internal"
    if CONFIDENTIAL.search(leaf):
        return "Confidential"
    return "Internal"


# ---------------------------------------------------------------- privacy tags
#
# Tags say WHAT kind of sensitive data a column holds (PII, card data, credentials, pay)
# and WHOSE it is (guest or employee); the Classification term says HOW to handle it.
# Rules look at the column name and its parent object, so a phone number under
# `customer` is guest PII while `restaurants.location.phone` is a business number.

TAGS = {
    "pii": ("PII", "#7C3AED", "Personal data: identifies, or can be linked to, a guest or employee (CCPA, GDPR)."),
    "pii-direct-identifier": ("PII: Direct Identifier", "#9333EA",
                              "Identifies a person on its own: name, email, phone, street address, precise location or a bar tab name."),
    "pii-indirect-identifier": ("PII: Indirect Identifier", "#A78BFA",
                                "A pseudonymous ID (employee or guest GUID) that identifies a person when joined to other data."),
    "pci": ("PCI: Card Data", "#DC2626", "Payment card attributes (card brand, first six or last four digits). Never store full card numbers."),
    "credential": ("Credential", "#B91C1C", "Secrets such as access tokens, passwords and passcodes."),
    "compensation": ("Compensation", "#D97706", "Wages, pay rates and tips paid to employees."),
    "data-subject-guest": ("Data Subject: Guest", "#0EA5E9", "The personal data in this column is about a restaurant guest."),
    "data-subject-employee": ("Data Subject: Employee", "#0284C7", "The personal data in this column is about a restaurant employee."),
}

EMPLOYEE_TABLES = re.compile(r"^labor\.(employees|shifts|timeEntries)$")
EMPLOYEE_REFS = {"server", "voiduser", "deliveryemployee", "employeereference", "employee", "employee1", "employee2",
                 "openedby", "approver", "createdby"}
EMPLOYEE_IDS = {"employeeid", "employeeids", "employeeguid", "v2employeeguid", "externalemployeeid"}
NAMES = {"firstname", "lastname", "chosenname", "employeefirstname", "employeelastname", "employeechosenname",
         "servername", "tabname"}
CONTACT = {"email", "phone", "phonenumber", "createdbyemailaddress"}
GUEST_ADDRESS = {"address1", "address2", "city", "state", "administrativearea", "zipcode", "latitude", "longitude"}
CARD = {"last4digits", "first6digits", "cardlast4digits", "cardtype", "paymentcardtype"}
PAY = {"wage", "defaultwage", "hourlywage"}
TIPS_PAID = {"declaredcashtips", "noncashtips", "noncashtipsroundingloss", "tipswithheld",
             "cashgratuityservicecharges", "noncashgratuityservicecharges"}
BUSINESS_CONTACT = {"phone", "phonecountrycode", "address1", "address2", "city", "zipcode", "latitude", "longitude"}


def privacy(table: str, path: str):
    """Return (tags, minimum tier, forced tier) for a column."""
    parts = path.split(".")
    leaf, parent = parts[-1].lower(), (parts[-2].lower() if len(parts) > 1 else "")
    lowered = [p.lower() for p in parts]
    # A restaurant's own published phone and address are business data, not personal data.
    if re.match(r"^(restaurants|partners)\.", table) and "location" in lowered and leaf in BUSINESS_CONTACT:
        return set(), None, "Internal"
    if leaf in ("phonecountrycode", "phonenumbercountrycode"):
        return set(), None, "Internal"  # not identifying on its own

    guest = any(p in ("customer", "deliveryinfo", "curbsidepickupinfo") for p in lowered) or leaf == "tabname"
    employee = bool(EMPLOYEE_TABLES.match(table)) or any(p in EMPLOYEE_REFS for p in lowered) \
        or leaf in EMPLOYEE_IDS or leaf.startswith("employee") or leaf == "servername"
    tags, tier = set(), None

    if leaf in NAMES:
        tags |= {"pii", "pii-direct-identifier"}; tier = "Confidential"
    elif leaf in CONTACT:
        tags |= {"pii", "pii-direct-identifier"}; tier = "Restricted"
    elif "deliveryinfo" in lowered and leaf in GUEST_ADDRESS:
        tags |= {"pii", "pii-direct-identifier"}; tier = "Confidential"
    elif leaf in ("notes", "transportdescription") and guest:
        tags |= {"pii"}; tier = "Confidential"  # free text written by or about the guest
    elif parts[-1] == "customer" or (leaf in ("guid", "externalid") and parent == "customer"):
        tags |= {"pii", "pii-indirect-identifier"}
    elif leaf in EMPLOYEE_IDS or leaf in EMPLOYEE_REFS or (leaf in ("guid", "externalid") and parent in EMPLOYEE_REFS) \
            or (table == "labor.employees" and parts[:2] == ["response", parts[-1]] and leaf in ("guid", "externalid")):
        tags |= {"pii", "pii-indirect-identifier"}; employee = True

    if leaf in CARD:
        tags.add("pci"); tier = "Restricted"
    if re.search(r"(password|secret|passcode|accesstoken|refreshtoken|idtoken|^token)$", leaf):
        tags.add("credential"); tier = "Restricted"
    if leaf in PAY or parent == "wageoverrides":
        tags.add("compensation"); tier = "Restricted"
        if EMPLOYEE_TABLES.match(table):
            tags.add("pii")
    if leaf in TIPS_PAID and EMPLOYEE_TABLES.match(table):
        tags |= {"compensation", "pii"}; tier = tier or "Confidential"

    if "pii" in tags:
        if guest:
            tags.add("data-subject-guest")
        elif employee:
            tags.add("data-subject-employee")
    return tags, tier, None


def classify_column(table: str, path: str):
    """Classification tier and privacy tags for a column."""
    tags, minimum, forced = privacy(table, path)
    if forced:
        return forced, tags
    level = classify(table, path)
    if minimum and LEVELS.index(minimum) > LEVELS.index(level):
        level = minimum
    return level, tags


def tag_urn(tag: str) -> str:
    return f"urn:li:tag:{tag}"


# ---------------------------------------------------------------- spec helpers


def resolve_pointer(spec: dict, ref: str):
    node = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def humanize(name: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).replace("_", " ").replace("-", " ")
    words = re.sub(r"\bGuid\b|\bGUID\b|\bguid\b", "GUID", words)
    return words.strip().lower().replace("guid", "GUID")


def clean(text) -> str:
    if not text:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", str(text))  # markdown links -> text
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1000]


def suggest_description(name: str, parent: str, kind: str, table: str) -> str:
    h = humanize(name)
    owner = humanize(parent) if parent else humanize(table)
    n = name.lower()
    if n in ("guid", "id", "uuid"):
        s = f"Unique identifier of the {owner}."
    elif n.endswith(("guid", "uuid", "id")) and n != "externalid":
        s = f"Unique identifier of the {re.sub(r' (GUID|uuid|id)$', '', h, flags=re.I)} associated with this {owner}."
    elif n == "externalid":
        s = f"Identifier assigned to the {owner} by an external partner system."
    elif n == "entitytype":
        s = f"Type of Toast platform entity that this {owner} object represents."
    elif n.startswith(("is", "has")) and len(n) > 3:
        s = f"Whether the {owner} {h.split(' ', 1)[1] if ' ' in h else h}."
    elif re.search(r"(date|time)$", n):
        s = f"Date and time of the {h.replace(' date', '').replace(' time', '')} for the {owner}."
    elif re.search(r"(amount|price|total|tax|tip|fee|charge)", n):
        s = f"Monetary value of the {h} for the {owner}."
    elif re.search(r"(count|quantity|size)$", n):
        s = f"Number of {h.replace(' count', '').replace(' quantity', '')} for the {owner}."
    elif n == "pagetoken":
        s = "Token returned by a previous request that selects the next page of results."
    elif n == "name":
        s = f"Display name of the {owner}."
    else:
        s = f"The {h} of the {owner}."
    if kind == "query":
        s = s.rstrip(".") + ". Provided as a query parameter to filter or page the request."
    elif kind == "path":
        s = s.rstrip(".") + ". Provided in the request URL path."
    return "Suggested: " + s


def sample_value(name: str, schema: dict, path: str, level: str) -> tuple:
    """Return (value, source) where source is 'spec' or 'synthetic'."""
    if level == "Restricted":
        return "•••• masked (Restricted)", "masked"
    for key in ("example", "x-example", "default"):
        if key in schema and not isinstance(schema[key], (dict, list)):
            return str(schema[key]), "spec"
    if schema.get("enum"):
        return str(schema["enum"][0]), "spec"
    n, t, fmt = name.lower(), schema.get("type"), schema.get("format", "")
    if fmt == "date-time" or re.search(r"(date|time)$", n) and t == "string":
        return "2026-03-14T18:25:43.511+0000", "synthetic"
    if fmt == "date":
        return "2026-03-14", "synthetic"
    if re.search(r"(guid|uuid|guids|ids)$", n) or fmt == "uuid" or n == "id":
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "toast-sample:" + path)), "synthetic"
    if t == "boolean":
        return "true", "synthetic"
    if t == "integer":
        return "1", "synthetic"
    if t == "number":
        return "12.50" if re.search(r"(amount|price|total|tax|tip|fee)", n) else "1.0", "synthetic"
    if t == "string":
        if n == "externalid":
            return "PARTNER-1001", "synthetic"
        if n == "entitytype":
            return humanize(name).title().replace(" ", ""), "synthetic"
        if n.endswith("firstname"):
            return "Jordan", "synthetic"
        if n.endswith("lastname"):
            return "Rivera", "synthetic"
        if "name" in n:
            return "Sample " + humanize(name).replace(" name", "").title(), "synthetic"
        return "sample", "synthetic"
    return "", "none"


def field_type(schema: dict) -> tuple:
    t, fmt = schema.get("type"), schema.get("format")
    if schema.get("enum"):
        return EnumTypeClass(), "enum"
    if t == "string" and fmt == "date-time":
        return TimeTypeClass(), "string(date-time)"
    if t == "string" and fmt == "date":
        return DateTypeClass(), "string(date)"
    if t in ("integer", "number"):
        return NumberTypeClass(), f"{t}({fmt})" if fmt else t
    if t == "boolean":
        return BooleanTypeClass(), "boolean"
    if t == "array":
        return ArrayTypeClass(nestedType=[schema.get("items", {}).get("type", "object")]), "array"
    if t == "object" or "properties" in schema:
        return RecordTypeClass(), "object"
    return StringTypeClass(), f"string({fmt})" if fmt else "string"


class Walker:
    """Flattens request parameters and response schemas into column dicts."""

    def __init__(self, spec: dict, table: str, qualified: str):
        # table is the resource name used in descriptions; qualified is "<api>.<table>" for classification rules.
        self.spec, self.table, self.qualified = spec, table, qualified
        self.columns: "OrderedDict[str, dict]" = OrderedDict()

    def resolve(self, schema, seen: tuple):
        """Resolve $ref/allOf/oneOf/anyOf. Returns (schema, seen, recursive_name)."""
        if not isinstance(schema, dict):
            return {}, seen, None
        while "$ref" in schema:
            name = schema["$ref"].split("/")[-1]
            if name in seen:
                return schema, seen, name
            seen = seen + (name,)
            target = resolve_pointer(self.spec, schema["$ref"])
            schema = {**target, **{k: v for k, v in schema.items() if k != "$ref"}}
        for combo in ("allOf", "oneOf", "anyOf"):
            if combo in schema:
                merged = {k: v for k, v in schema.items() if k != combo}
                for part in schema[combo]:
                    # Inherited definitions (allOf) are not ancestors: a Check and its parent Order both
                    # inherit ExternalReference, and that is not recursion. Only property $refs count.
                    part, _, rec = self.resolve(part, ())
                    if rec:
                        continue
                    if "properties" in part:
                        merged.setdefault("properties", {}).update(part["properties"])
                    for k, v in part.items():
                        if k not in ("properties", "required"):
                            merged.setdefault(k, v)
                schema = merged
        return schema, seen, None

    def add(self, path, name, parent, schema, kind, recursive=None):
        if path in self.columns:
            return
        level, tags = classify_column(self.qualified, path)
        desc = clean(schema.get("description"))
        source = "spec"
        if recursive:
            desc = (desc + " " if desc else "") + f"Recursive reference to {recursive}; nested fields are listed once at its first appearance."
        if not desc:
            desc, source = suggest_description(name, parent, kind, self.table), "suggested"
        dtype, native = field_type(schema)
        sample, sample_source = sample_value(name, schema, path, level)
        self.columns[path] = dict(
            path=path, desc=desc, desc_source=source, type=dtype, native=native,
            level=level, tags=sorted(tags), sample=sample, sample_source=sample_source,
            nullable=kind == "response", recursive=bool(recursive),
        )

    def walk(self, schema, path: str, name: str, parent: str, depth: int, seen: tuple):
        schema, seen, rec = self.resolve(schema, seen)
        if rec:
            self.add(path, name, parent, {"type": "object", "description": schema.get("description")}, "response", rec)
            return
        if path != "response":
            self.add(path, name, parent, schema, "response")
        if depth >= MAX_DEPTH:
            return
        if schema.get("type") == "array" or "items" in schema:
            self.walk(schema.get("items", {}), path, name, parent, depth, seen)
            return
        for prop, sub in (schema.get("properties") or {}).items():
            self.walk(sub, f"{path}.{prop}", prop, name, depth + 1, seen)

    def parameter(self, param: dict):
        param, _, _ = self.resolve(param, ())
        where = param.get("in")
        if where not in ("query", "path"):
            return
        schema = param.get("schema", param)
        schema, _, _ = self.resolve(schema, ())
        merged = {**schema, "description": param.get("description") or schema.get("description")}
        for k in ("example", "x-example"):
            if k in param:
                merged[k] = param[k]
        self.add(f"{where}.{param['name']}", param["name"], self.table, merged, where)


def success_schema(op: dict):
    for code in ("200", "201", "202", 200, 201, 202):
        resp = (op.get("responses") or {}).get(code)
        if resp is None:
            continue
        if "schema" in resp:
            return resp["schema"]
        for media, body in (resp.get("content") or {}).items():
            if "json" in media and "schema" in body:
                return body["schema"]
    return None


def table_for(path: str) -> str:
    for seg in path.strip("/").split("/"):
        if seg and not seg.startswith("{") and seg.lower() not in SKIP_SEGMENTS:
            return seg
    return "root"


def base_path(spec: dict) -> str:
    if "basePath" in spec:
        return spec["basePath"]
    servers = spec.get("servers") or [{}]
    return "/" + servers[0].get("url", "").split("://")[-1].split("/", 1)[-1]


# ---------------------------------------------------------------- build


def build():
    now = int(time.time() * 1000)
    stamp = AuditStampClass(time=now, actor="urn:li:corpuser:datahub")
    mcps, summary = [], []

    mcps.append(MetadataChangeProposalWrapper(
        entityUrn=PLATFORM_URN,
        aspect=DataPlatformInfoClass(name=PLATFORM, displayName="Toast API", type="OTHERS", datasetNameDelimiter="."),
    ))

    mcps.append(MetadataChangeProposalWrapper(
        entityUrn=CLASSIFICATION_NODE,
        aspect=GlossaryNodeInfoClass(
            name="Classification",
            definition="Data classification tiers. Each column in the Toast API catalog carries exactly one tier.",
        ),
    ))
    for level in LEVELS:
        mcps.append(MetadataChangeProposalWrapper(
            entityUrn=term_urn(level),
            aspect=GlossaryTermInfoClass(
                name=level, definition=LEVEL_RULES[level], termSource="INTERNAL",
                parentNode=CLASSIFICATION_NODE, customProperties={"tier": str(LEVELS.index(level) + 1)},
            ),
        ))
    for tag, (name, color, desc) in TAGS.items():
        mcps.append(MetadataChangeProposalWrapper(
            entityUrn=tag_urn(tag), aspect=TagPropertiesClass(name=name, description=desc, colorHex=color)))

    for file, (display, slug) in APIS.items():
        spec = yaml.safe_load((SPECS / file).read_text(encoding="utf-8"))
        info = spec.get("info", {})
        base = base_path(spec)
        key = ToastApiKey(platform=PLATFORM, env="PROD", api=slug)
        container_urn = key.as_urn()
        for wu in gen_containers(
            container_key=key, name=display, sub_types=["Schema"],
            description=clean(info.get("description")) or f"Toast {display} API.",
            external_url=DOCS.format(slug=slug),
            extra_properties={"api_version": str(info.get("version")), "base_path": base, "spec_file": file},
        ):
            mcps.append(wu.metadata)

        tables: "OrderedDict[str, list]" = OrderedDict()
        for p, ops in spec.get("paths", {}).items():
            tables.setdefault(table_for(p), []).append((p, ops))

        for table, endpoints in tables.items():
            walker = Walker(spec, table, f"{slug}.{table}")
            endpoint_lines, summaries = [], []
            for p, ops in endpoints:
                shared = ops.get("parameters", [])
                for method in HTTP_METHODS:
                    op = ops.get(method)
                    if not op:
                        continue
                    endpoint_lines.append(f"{method.upper()} {base}{p}")
                    if op.get("summary"):
                        summaries.append(f"`{method.upper()} {p}`: {clean(op['summary'])}")
                    for param in shared + op.get("parameters", []):
                        walker.parameter(param)
                    schema = success_schema(op)
                    if schema:
                        walker.walk(schema, "response", table, table, 0, ())
            cols = list(walker.columns.values())

            urn = make_dataset_urn(PLATFORM, f"{slug}.{table}", "PROD")
            levels = Counter(c["level"] for c in cols)
            top = max((c["level"] for c in cols), key=LEVELS.index, default="Internal")
            table_tags = sorted({t for c in cols for t in c["tags"]})
            desc = (
                f"Suggested: The `{table}` resource of the Toast {display} API. "
                f"It covers {len(endpoint_lines)} endpoint{'s' if len(endpoint_lines) != 1 else ''}"
                + (":\n\n- " + "\n- ".join(summaries) if summaries else ".")
                + f"\n\nHighest column classification: **{top}**."
                + f"\n\n{COLUMN_GUIDE}"
            )
            kinds = Counter(c["path"].split(".")[0] for c in cols)
            mcps += [
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=DatasetPropertiesClass(
                    name=table, description=desc, externalUrl=DOCS.format(slug=slug),
                    customProperties={
                        "api": display, "api_version": str(info.get("version")),
                        "endpoints": "; ".join(endpoint_lines),
                        "highest_classification": top,
                        **{f"columns_{lvl.lower()}": str(levels.get(lvl, 0)) for lvl in LEVELS},
                        "response_fields": str(kinds.get("response", 0)),
                        "query_parameters": str(kinds.get("query", 0)),
                        "path_parameters": str(kinds.get("path", 0)),
                        "description_note": "Descriptions starting with 'Suggested:' were generated, not taken from Toast's spec.",
                        "sample_note": "Sample values come from spec examples where present; others are synthetic placeholders. Restricted columns are masked.",
                    },
                )),
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=SubTypesClass(typeNames=["Table"])),
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=DataPlatformInstanceClass(platform=PLATFORM_URN)),
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=ContainerClass(container=container_urn)),
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=BrowsePathsV2Class(
                    path=[BrowsePathEntryClass(id=container_urn, urn=container_urn)])),
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=StatusClass(removed=False)),
                # Classification tier plus the business entity terms from the platform glossary (Order, Check...).
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlossaryTermsClass(
                    terms=[GlossaryTermAssociationClass(urn=u) for u in
                           [term_urn(top), *TABLE_TERMS.get(urn, []), *([API_TABLE_TERM] if API_TABLE_TERM else [])]],
                    auditStamp=stamp)),
                # Table-level tags roll up the column tags, so "tables with guest PII" is one search filter.
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlobalTagsClass(
                    tags=[TagAssociationClass(tag=tag_urn(t)) for t in table_tags])),
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=SchemaMetadataClass(
                    schemaName=f"{slug}.{table}", platform=PLATFORM_URN, version=0, hash="",
                    platformSchema=OtherSchemaClass(rawSchema=""),
                    fields=[
                        SchemaFieldClass(
                            fieldPath=c["path"], type=SchemaFieldDataTypeClass(type=c["type"]),
                            nativeDataType=c["native"], description=c["desc"], nullable=c["nullable"],
                            recursive=c["recursive"],
                            glossaryTerms=GlossaryTermsClass(
                                terms=[GlossaryTermAssociationClass(urn=term_urn(c["level"]))], auditStamp=stamp),
                            globalTags=GlobalTagsClass(tags=[TagAssociationClass(tag=tag_urn(t)) for t in c["tags"]])
                            if c["tags"] else None,
                        )
                        for c in cols
                    ],
                )),
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=DatasetProfileClass(
                    timestampMillis=now, columnCount=len(cols),
                    fieldProfiles=[
                        DatasetFieldProfileClass(fieldPath=c["path"], sampleValues=[c["sample"]])
                        for c in cols if c["sample"]
                    ],
                )),
            ]
            summary.append(dict(
                api=display, table=table, urn=urn, columns=len(cols), endpoints=len(endpoint_lines),
                top=top, levels=dict(levels), tags=table_tags,
                tag_counts=dict(Counter(t for c in cols for t in c["tags"])),
                suggested=sum(c["desc_source"] == "suggested" for c in cols),
                spec_samples=sum(c["sample_source"] == "spec" for c in cols),
            ))
    return mcps, summary


def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="send the metadata to DataHub")
    args = ap.parse_args()

    mcps, summary = build()
    OUT.mkdir(exist_ok=True)
    (OUT / "metadata.json").write_text(json.dumps([m.to_obj() for m in mcps], indent=1), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")

    current = None
    for s in summary:
        if s["api"] != current:
            current = s["api"]
            print(f"\n{current}")
        lv = " ".join(f"{k[0]}{s['levels'].get(k, 0)}" for k in LEVELS)
        print(f"  {s['table']:<28} cols={s['columns']:<4} endpoints={s['endpoints']:<2} top={s['top']:<12} [{lv}] suggested={s['suggested']}")
    print(f"\n{len(summary)} tables, {sum(s['columns'] for s in summary)} columns, {len(mcps)} aspects -> out/metadata.json")

    if args.push:
        load_env()
        server, token = os.environ.get("DATAHUB_GMS_URL"), os.environ.get("DATAHUB_TOKEN")
        if not server or not token:
            print("DATAHUB_GMS_URL and DATAHUB_TOKEN must be set (environment or .env).")
            return 1
        from datahub.emitter.rest_emitter import DatahubRestEmitter

        emitter = DatahubRestEmitter(gms_server=server, token=token)
        emitter.test_connection()
        for i, mcp in enumerate(mcps, 1):
            emitter.emit(mcp)
            if i % 200 == 0:
                print(f"  pushed {i}/{len(mcps)}")
        emitter.close()
        print(f"Pushed {len(mcps)} aspects to {server}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
