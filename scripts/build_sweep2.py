"""Second sweep: everything in the archive from the past 12 months and forward
that has not been screened yet, under the wider rules (pending votes first).

Keeps an item if it has a discretionary category, or it is large: $1M+ when
the vote is still ahead, $5M+ when the meeting has passed. Routine and
narrative text, money coming in, duplicates and anything already screened
(review sheet, backlog list, first sweep) are dropped.
Writes data/sweep2/lane_<k>.json.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_candidates import tag_stage_category  # noqa: E402
from build_backlog import ROUTINE, NARRATIVE  # noqa: E402
import archive_items  # noqa: E402
import rules  # noqa: E402

LANES = 10
DISC = {"outgoing_grant", "no_bid", "vanity", "officials_perks", "private_benefit", "facilities", "consultants", "legal"}


def main():
    today = datetime.now(timezone.utc).date()
    cutoff = (today - timedelta(days=365)).isoformat()
    seen = {r["item_id"] for r in json.loads((ROOT / "data/review_export.json").read_text())["rows"]}
    seen |= {i["id"] for i in json.loads((ROOT / "data/backlog_candidates.json").read_text())["items"]}
    for f in (ROOT / "data/sweep").glob("lane_*.json"):
        seen |= {i["id"] for i in json.loads(f.read_text())["items"]}
    out, tkeys, akeys = [], set(), set()
    for f in sorted((ROOT / "data/archive").glob("*.json")):
        if f.stem != "undated" and f.stem < cutoff[:7]:
            continue
        for k, r in archive_items.load(str(f)).items():
            md = r.get("meeting_date") or ""
            if md < cutoff or k in seen:
                continue
            tags = rules.classify(r.get("title") or "")
            if not tags:
                continue
            it = tag_stage_category({**r, **tags}, today)
            if it.get("flow") == "in":
                continue
            t = " ".join((it.get("title") or "").split())
            if len(t) < 40 or ROUTINE.search(t) or NARRATIVE.search(t):
                continue
            amt = abs(it.get("max_amount") or 0)
            pending = it["stage"] in ("upcoming", "early_warning")
            if not (set(it["categories"]) & DISC or amt >= (1e6 if pending else 5e6)):
                continue
            tk = (it.get("entity_id"), t[:160].lower())
            ak = (it.get("entity_id"), round(amt), md)
            if tk in tkeys or (amt and ak in akeys):
                continue
            tkeys.add(tk); akeys.add(ak)
            out.append({"id": k, "government": it.get("government"), "body": it.get("body"), "meeting_date": md,
                        "stage": it["stage"], "days_until_meeting": it.get("days_until_meeting"),
                        "categories": it["categories"], "amount": it.get("max_amount"), "flow": it.get("flow"),
                        "passed": it.get("passed"), "recipient": it.get("recipient"), "link": it["link"],
                        "project_id": it.get("project_id"), "project_total": it.get("project_total"),
                        "funding_source": it.get("funding_source"), "paying_fund": it.get("paying_fund"),
                        "paying_fund_expenditures": it.get("paying_fund_expenditures"),
                        "pct_of_paying_fund": it.get("pct_of_paying_fund"),
                        "possible_duplicate_label": it.get("possible_duplicate_label"), "text": t[:900]})
    pend = sorted([x for x in out if x["stage"] in ("upcoming", "early_warning")], key=lambda x: x["meeting_date"])
    past = sorted([x for x in out if x["stage"] not in ("upcoming", "early_warning")], key=lambda x: x["meeting_date"], reverse=True)
    items = pend + past
    d = ROOT / "data/sweep2"
    d.mkdir(exist_ok=True)
    lanes = [items[k::LANES] for k in range(LANES)]
    for k, lane in enumerate(lanes, 1):
        for n, x in enumerate(lane, 1):
            x["n"] = n
        (d / f"lane_{k}.json").write_text(json.dumps({"lane": k, "count": len(lane), "items": lane}, indent=0, ensure_ascii=False))
    print(len(items), "pending", len(pend), "past", len(past), [len(l) for l in lanes])


if __name__ == "__main__":
    main()
