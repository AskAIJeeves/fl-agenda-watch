"""One-time backlog list for review: archive items whose meeting has passed,
pre-filtered and put in priority order, for a scheduled Claude task to score
with the digest rubric and add to the review Sheet's Backlog tab.
Writes data/backlog_candidates.json.

Priority groups: 1 big commitments (facilities or debt >= $5M), 2 private
benefit, 3 outgoing grants, 4 no-bid, 5 vanity / officials / consultants.
Items that are only "large spending" are left out.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_candidates import tag_stage_category  # noqa: E402
import archive_items  # noqa: E402
import rules  # noqa: E402

ROUTINE = re.compile(r"(?i)check register|millage|warrant list|minutes of|budget (amendment|transfer|adjustment)|"
                     r"supplemental budget|payroll|insurance renewal|tentative budget|final budget|budget hearing|"
                     r"roll call|pledge of allegiance|consent agenda")
# Minutes and staff narrative rather than an item: often start with these.
NARRATIVE = re.compile(r"(?i)^(continuing|mr\.|ms\.|mrs\.|the emergency was)|^[^.]{0,80}\b(explained|asked|said|noted|stated|reviewed|presented)\b|grant application|apply for (a |the )?grant")


def group(it):
    c = set(it["categories"])
    amt = it.get("max_amount") or 0
    if ("facilities" in c or "debt" in c) and amt >= 5e6:
        return 1
    if "private_benefit" in c:
        return 2
    if "outgoing_grant" in c:
        return 3
    if "no_bid" in c:
        return 4
    if c & {"vanity", "officials_perks", "consultants"}:
        return 5
    return None


def main():
    today = datetime.now(timezone.utc).date()
    seen, out = set(), []
    for f in sorted((ROOT / "data/archive").glob("*.json")):
        for k, r in archive_items.load(str(f)).items():
            tags = rules.classify(r.get("title") or "")     # re-run current rules (new signals, exclusions)
            if not tags:
                continue
            it = tag_stage_category({**r, **tags}, today)
            if it["stage"] in ("upcoming", "early_warning"):
                continue                     # the daily digest covers these
            t = " ".join((it.get("title") or "").split())
            if len(t) < 40 or ROUTINE.search(t) or NARRATIVE.search(t):
                continue
            g = group(it)
            if not g:
                continue
            dk = (it.get("entity_id"), t[:160].lower())
            if dk in seen:
                continue
            seen.add(dk)
            out.append({"id": k, "group": g, "government": it.get("government"), "body": it.get("body"),
                        "meeting_date": it.get("meeting_date"), "stage": it["stage"], "categories": it["categories"],
                        "amount": it.get("max_amount"), "passed": it.get("passed"), "recipient": it.get("recipient"),
                        "signal_score": it.get("signal_score"), "link": it["link"], "text": t[:900]})
    out.sort(key=lambda x: (x["group"], -(x["signal_score"] or 0), x["meeting_date"] or "0000"), reverse=False)
    # bound the review work: at most PER_GOV items per government and TOTAL overall, in priority order
    PER_GOV, TOTAL, kept, per = 45, 700, [], {}
    for x in out:
        if per.get(x["government"], 0) < PER_GOV and len(kept) < TOTAL:
            kept.append(x)
            per[x["government"]] = per.get(x["government"], 0) + 1
    out = kept
    for i, x in enumerate(out, 1):
        x["n"] = i
    counts = {g: sum(1 for x in out if x["group"] == g) for g in range(1, 6)}
    (ROOT / "data/backlog_candidates.json").write_text(json.dumps(
        {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "count": len(out),
         "by_group": counts, "items": out}, indent=1, ensure_ascii=False))
    print(len(out), counts)


if __name__ == "__main__":
    main()
