"""Group archived items into projects (the highest-level unique deal or
purchase) so dollars can be totaled without double counting.

Project id, first rule that applies:
  1. A curated committed project (config/committed_projects.json): same
     government and a keyword match. id = "cp:<id>".
  2. A reference number shared across items of one government: ordinance or
     resolution number, bid/RFP/ITB/contract number, or Legistar file number.
     id = "<entity>|ref:<normalized ref>".
  3. Otherwise the item stands alone. id = "<entity>|item:<item key>".

Project total, without double counting:
  - committed projects: the curated total_cost;
  - otherwise: spending items (flow "out"/"mixed") with the same amount are
    counted once (an appropriation, contract award and purchase order for the
    same money), then distinct amounts are summed. Receipts are totaled
    separately as negatives.
Totals are estimates from agenda text; total_method says how each was made.
Writes data/projects.json: {"projects": {...}, "item_project": {item key: project id}}.
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import archive_items  # noqa: E402
import rules  # noqa: E402

REF = re.compile(r"(?i)\b(?:(ordinance|ord\.?|resolution|res\.?)\s*(?:no\.?|number|#)?\s*(\d{2,4}-[A-Z]?\d{1,5}(?:-[A-Z])?)|"
                 r"(bid|rfp|rfq|itb|ifb|rfs|solicitation|contract)\s*(?:no\.?|number|#)\s*([A-Z0-9][A-Z0-9-]{3,20}))")


def refs(text):
    """Reference numbers that identify the item itself. An ordinance or resolution number counts only
    near the start of the text (the item's own number); deeper in, it is usually a citation of another
    act, such as the annual budget ordinance, and would wrongly merge unrelated items."""
    out = set()
    for m in REF.finditer(text or ""):
        if m.group(2) and m.start() > 40:
            continue
        if m.group(2):
            out.add("ord/res " + m.group(2).upper().rstrip("-E").rstrip("-"))
        elif m.group(4):
            out.add(m.group(3).lower() + " " + m.group(4).upper())
    return out


def main():
    cps = json.loads((ROOT / "config/committed_projects.json").read_text())["projects"]
    items = {}
    for f in sorted((ROOT / "data/archive").glob("*.json")):
        items.update(archive_items.load(str(f)))

    # pass 1: references per item, and how many items share each reference
    item_refs, ref_count = {}, defaultdict(int)
    for k, r in items.items():
        ent = r.get("entity_id") or r.get("government")
        rs = {f"{ent}|ref:{x}" for x in refs(r.get("title"))}
        if r.get("client") not in (None, "pdf") and r.get("file_number"):
            rs.add(f"{ent}|ref:file {r['file_number']}")
        item_refs[k] = sorted(rs)
        for x in rs:
            ref_count[x] += 1

    item_project, members = {}, defaultdict(list)
    for k, r in items.items():
        text, gov = (r.get("title") or "").lower(), (r.get("government") or "").lower()
        pid = None
        for cp in cps:
            g = cp["government"].lower().replace("city of ", "").replace(" county", "")
            if g in gov and any(kw.lower() in text for kw in cp.get("keywords", [])):
                pid = "cp:" + cp["id"]
                break
        if not pid:
            shared = [x for x in item_refs[k] if ref_count[x] > 1]
            pid = shared[0] if shared else (item_refs[k][0] if item_refs[k] else
                                             f"{r.get('entity_id')}|item:{k}")
        item_project[k] = pid
        members[pid].append(k)

    projects = {}
    for pid, ks in members.items():
        rs = [items[k] for k in ks]
        spend, receipts = set(), set()
        for r in rs:
            amt = r.get("max_amount")
            if not amt:
                continue
            fl = r.get("flow") or rules.flow(r.get("title") or "")
            (receipts if fl == "in" else spend).add(round(amt, -2))   # same money approved twice counts once
        cp = next((c for c in cps if "cp:" + c["id"] == pid), None)
        if cp and cp.get("total_cost"):
            total, method = cp["total_cost"], "curated"
        else:
            total = sum(spend) if spend else None
            method = "distinct amounts summed" if len(spend) > 1 else "single amount" if spend else "no amount"
        dates = sorted(d for d in (r.get("meeting_date") for r in rs) if d)
        projects[pid] = {
            "government": rs[0].get("government"),
            "name": cp["project"] if cp else (rs[0].get("title") or "")[:160],
            "items": len(ks), "spend_total": total, "receipts_total": -sum(receipts) if receipts else None,
            "total_method": method, "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
        }
    (ROOT / "data/projects.json").write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "projects": dict(sorted(projects.items())), "item_project": dict(sorted(item_project.items()))},
        indent=0, ensure_ascii=False))
    multi = sum(1 for p in projects.values() if p["items"] > 1)
    print(f"projects: {len(projects)} from {len(items)} items; {multi} group more than one item")


if __name__ == "__main__":
    main()
