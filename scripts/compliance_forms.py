"""Create the Toast compliance forms and assign them.

  Toast KPI Certification      KPI, non-GAAP and revenue stream terms   -> term owners + you
  Restricted Data Attestation  Toast API tables classified Restricted   -> table owners + you

Both are VERIFICATION forms: once every prompt is answered, the responder verifies the
asset, which is the evidence trail for the certification. Safe to rerun.
"""

import json
from pathlib import Path

from business_glossary import TERMS, term_urn
from dh import gql

ROOT = Path(__file__).resolve().parent.parent


def sp(pid):
    return f"urn:li:structuredProperty:{pid}"


def prompt(pid, title, desc, prop):
    return {"id": pid, "title": title, "description": desc, "type": "STRUCTURED_PROPERTY",
            "structuredPropertyParams": {"urn": sp(prop)}, "required": True}


FORMS = {
    "toast-kpi-certification": dict(
        name="Toast KPI Certification",
        description="Quarterly certification of Toast's reported KPIs and financial definitions. The owning functional unit "
                    "confirms the definition still matches the latest 10-K or 10-Q and records the certification date. "
                    "Recertify after each filing.",
        prompts=[
            prompt("kpi-status", "Certification status",
                   "Set to Certified once the definition matches the most recent filing, or Deprecated if Toast stopped reporting it.",
                   "toast.certificationStatus"),
            prompt("kpi-date", "Date certified", "The date you reviewed the definition against the filing.", "toast.lastCertifiedDate"),
        ],
        entities=lambda: [term_urn(k) for k, t in TERMS.items() if t[0] in ("kpi", "nongaap", "revenue")],
    ),
    "toast-restricted-data-attestation": dict(
        name="Restricted Data Attestation",
        description="Owners of Toast API tables that hold Restricted data (card, contact, credential or pay data) confirm the "
                    "classification is correct and certify the table. This clears the 'Restricted Toast API tables are "
                    "certified' metadata test.",
        prompts=[
            prompt("rda-class", "Confirm data classification",
                   "Confirm the highest classification of data in this table. Change it if the automatic classification is wrong.",
                   "toast.dataClassification"),
            prompt("rda-status", "Certification status", "Set to Certified once access and masking rules are confirmed.",
                   "toast.certificationStatus"),
            prompt("rda-date", "Date certified", "The date of this attestation.", "toast.lastCertifiedDate"),
        ],
        entities=lambda: [s["urn"] for s in json.loads((ROOT / "out" / "summary.json").read_text(encoding="utf-8"))
                          if s["top"] == "Restricted"],
    ),
}


def main() -> int:
    me = gql("{ me { corpUser { urn } } }")["me"]["corpUser"]["urn"]
    for fid, f in FORMS.items():
        urn = f"urn:li:form:{fid}"
        try:
            gql("mutation($i: CreateFormInput!) { createForm(input: $i) { urn } }", {"i": {
                "id": fid, "name": f["name"], "description": f["description"], "type": "VERIFICATION",
                "prompts": f["prompts"], "actors": {"owners": True, "users": [me]},
            }})
            print(f"created  {f['name']}")
        except RuntimeError as e:
            if "already exists" not in str(e):
                raise
            print(f"exists   {f['name']}")
        entities = f["entities"]()
        gql("mutation($i: BatchAssignFormInput!) { batchAssignForm(input: $i) }",
            {"i": {"formUrn": urn, "entityUrns": entities}})
        # Tables can be reclassified; take the attestation off tables that are no longer Restricted.
        if fid == "toast-restricted-data-attestation":
            stale = [s["urn"] for s in json.loads((ROOT / "out" / "summary.json").read_text(encoding="utf-8"))
                     if s["urn"] not in entities]
            gql("mutation($i: BatchRemoveFormInput!) { batchRemoveForm(input: $i) }",
                {"i": {"formUrn": urn, "entityUrns": stale}})
        # Forms created through the API start as DRAFT; assignees only see PUBLISHED forms as tasks.
        gql("mutation($i: UpdateFormInput!) { updateForm(input: $i) { urn } }", {"i": {"urn": urn, "state": "PUBLISHED"}})
        print(f"assigned and published {f['name']} on {len(entities)} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
