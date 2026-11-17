"""Merge both readers into one ranked candidate list for the daily digest, and keep a running
ledger of outgoing grant recipients across all governments."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rules
from archive_items import key as archive_key
import dupes
_DUP = None

def load(name):
    p = ROOT / "data" / name
    return json.loads(p.read_text()) if p.exists() else {"items": []}

EARLY = __import__("re").compile(r"(?i)workshop|work session|budget hearing|budget workshop|retreat|committee of the whole|agenda review|strategic planning")
DEBT = __import__("re").compile(r"(?i)\b(bonds?|loan|debt|refund(ing)?|line of credit|note[s]? payable|financing)\b")

def best_link(it):
    """Most specific link: the item's own page, else the PDF opened at the right page, else the meeting page."""
    if it.get("item_url"): return it["item_url"]
    pdf, pg = it.get("agenda_pdf"), str(it.get("agenda_number") or "")
    if pdf and pg.startswith("p.") and "#" not in pdf and not pdf.endswith("lang=English"):
        return f"{pdf}#page={pg[2:]}"
    return pdf or it.get("meeting_url")

_PJ = None
def project_of(key):
    """(project_id, project spend total) from data/projects.json, built nightly from the archive."""
    global _PJ
    if _PJ is None:
        p = ROOT / "data/projects.json"
        _PJ = json.loads(p.read_text()) if p.exists() else {"projects": {}, "item_project": {}}
    pid = _PJ["item_project"].get(key)
    return pid, (_PJ["projects"].get(pid) or {}).get("spend_total")

_BUD = None
def budget_of(eid):
    """General fund spending for the government (EDR/DFS Annual Financial Report, latest year)."""
    global _BUD
    if _BUD is None:
        p = ROOT / "data/budgets.json"
        _BUD = json.loads(p.read_text())["governments"] if p.exists() else {}
    return _BUD.get(eid) or {}

def budget_share(it, bud):
    """Size of the item against the fund group that pays for it. General fund when the text names it or names no source;
    otherwise the matching fund group from the Annual Financial Report (enterprise, special revenue, ...)."""
    src = it.get("funding_source") or rules.funding_source(it.get("title") or "")
    group = "general" if src in ("general", "unstated") else src
    base = (bud.get("fund_expenditures") or {}).get(group) or (bud.get("general_fund_expenditures") if group == "general" else None)
    amt = it.get("max_amount")
    pct = round(100 * amt / base, 3) if base and amt else None
    return {"funding_source": src, "paying_fund": group, "paying_fund_expenditures": base, "pct_of_paying_fund": pct,
            "general_fund": bud.get("general_fund_expenditures"),
            "pct_of_general_fund": pct if group == "general" else None}

def tag_stage_category(it, today):
    fresh = rules.classify(it.get("title") or "")       # re-apply current rules (new signals, flow) to stored items
    if fresh:
        it.update(fresh)
    it["link"] = best_link(it)
    it["id"] = archive_key(it)        # same key as data/archive and the review queue
    it["project_id"], it["project_total"] = project_of(it["id"])
    it.update(budget_share(it, budget_of(it.get("entity_id"))))
    global _DUP
    if _DUP is None: _DUP = dupes.Index()
    it["possible_duplicates"] = _DUP.find(it["id"], it.get("entity_id"), it.get("meeting_date"), it.get("max_amount"), it.get("title"))
    it["possible_duplicate_label"] = dupes.label(it["possible_duplicates"], it.get("meeting_date"))
    md = it.get("meeting_date")
    days = (datetime.fromisoformat(md).date() - today).days if md else None
    early = bool(EARLY.search(it.get("body") or ""))
    if days is None: stage = "undated"
    elif days >= 0: stage = "early_warning" if early else "upcoming"
    else: stage = "past_meeting"          # outcome of the vote is not verified
    it["stage"], it["days_until_meeting"] = stage, days
    sig = set(it.get("signals") or [])
    cats = []
    if it.get("outgoing_grant"): cats.append("outgoing_grant")
    if it.get("bypass_competition"): cats.append("no_bid")
    if "vanity" in sig: cats.append("vanity")
    if "officials" in sig: cats.append("officials_perks")
    if "facilities" in sig: cats.append("facilities")
    if "consultants" in sig: cats.append("consultants")
    if DEBT.search(it.get("title") or ""): cats.append("debt")
    if "legal" in sig: cats.append("legal")
    if "private_benefit" in sig: cats.append("private_benefit")
    it["categories"] = cats or ["large_spending"]
    return it

def main():
    now = datetime.now(timezone.utc); today = now.date()
    items = load("agenda_items.json")["items"] + load("pdf_items.json")["items"]
    pool, seen = [], set()
    for it in items:
        if "signal_score" not in it:                     # older rows from before shared rules
            t = rules.classify(it.get("title") or "")
            if not t: continue
            it.update(t)
        md = it.get("meeting_date"); fu = it.get("found_utc")
        recent_meeting = md and -3 <= (datetime.fromisoformat(md).date() - today).days <= 21
        recent_find = fu and (now - datetime.fromisoformat(fu)) <= timedelta(days=3)
        if not (recent_meeting or recent_find): continue
        key = (it["entity_id"], (it.get("title") or "")[:120])
        if key in seen: continue
        seen.add(key); pool.append(tag_stage_category(it, today))
    stage_rank = {"upcoming": 0, "early_warning": 0, "past_meeting": 1, "undated": 2}
    pool.sort(key=lambda x: (stage_rank[x["stage"]], -(x.get("signal_score") or 0)))
    grants = [x for x in pool if x.get("outgoing_grant")]
    bypass = [x for x in pool if x.get("bypass_competition") and not x.get("outgoing_grant")]
    rest = [x for x in pool if not x.get("outgoing_grant") and not x.get("bypass_competition")][:150]
    from collections import Counter
    out = {"generated_utc": now.isoformat(timespec="seconds"),
           "counts": {"pool": len(pool), "outgoing_grants": len(grants), "bypass": len(bypass), "other_top": len(rest),
                      "by_stage": dict(Counter(x["stage"] for x in pool)),
                      "by_category": dict(Counter(c for x in pool for c in x["categories"]))},
           "upcoming": sorted([x for x in pool if x["stage"] in ("upcoming", "early_warning")], key=lambda x: (x["days_until_meeting"], -(x.get("signal_score") or 0)))[:200],
           "outgoing_grants": grants, "bypass_competition": bypass, "other": rest}
    out["counts"]["possible_duplicates"] = sum(1 for x in pool if x.get("possible_duplicate_label"))
    out["counts"]["missing_link"] = sum(1 for x in pool if not x.get("link"))
    (ROOT / "data/candidates.json").write_text(json.dumps(out, indent=1))

    # running ledger of outgoing grant recipients (all time, all governments)
    lp = ROOT / "data/grant_recipients.json"
    ledger = json.loads(lp.read_text()) if lp.exists() else {"recipients": {}}
    for g in [x for x in items if x.get("outgoing_grant") and x.get("recipient")]:
        k = rules.norm(g["recipient"])
        if not k: continue
        r = ledger["recipients"].setdefault(k, {"name": g["recipient"], "awards": []})
        ref = (g["entity_id"], g.get("meeting_date"), g.get("max_amount"), (g.get("title") or "")[:80])
        if any((a["entity_id"], a["meeting_date"], a["amount"], a["text"][:80]) == ref for a in r["awards"]): continue
        r["awards"].append({"entity_id": g["entity_id"], "government": g["government"], "meeting_date": g.get("meeting_date"),
                            "amount": g.get("max_amount"), "text": (g.get("title") or "")[:300], "link": g.get("agenda_pdf") or g.get("meeting_url")})
    for r in ledger["recipients"].values():
        r["governments"] = sorted({a["government"] for a in r["awards"]})
        r["award_count"] = len(r["awards"]); r["total_amount"] = sum(a["amount"] or 0 for a in r["awards"])
    ledger["generated_utc"] = now.isoformat(timespec="seconds")
    ledger["multi_government"] = sorted([k for k, r in ledger["recipients"].items() if len(r["governments"]) > 1],
                                        key=lambda k: -ledger["recipients"][k]["total_amount"])
    lp.write_text(json.dumps(ledger, indent=1))
    print(out["counts"], "recipients:", len(ledger["recipients"]), file=sys.stderr)

if __name__ == "__main__":
    main()
