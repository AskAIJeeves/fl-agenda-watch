"""One-time sweep of candidates the daily digest never got to.

Takes every item in data/candidates.json that is not already in the review sheet
(data/review_export.json) or the earlier backlog list, carries a discretionary
category, and is not money coming in. Collapses same-government same-amount
duplicates, orders upcoming votes first, then past meetings (newest first), then
undated, and splits the list into LANES files so several scheduled runs can work
in parallel. Writes data/sweep/lane_<k>.json.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANES = 6
DISCRETIONARY = {"outgoing_grant", "no_bid", "vanity", "officials_perks", "private_benefit", "facilities", "consultants", "legal"}


def main():
    c = json.loads((ROOT / "data/candidates.json").read_text())
    seen_ids = {r["item_id"] for r in json.loads((ROOT / "data/review_export.json").read_text())["rows"]}
    seen_ids |= {i["id"] for i in json.loads((ROOT / "data/backlog_candidates.json").read_text())["items"]}
    pool = {}
    for k in ("upcoming", "outgoing_grants", "bypass_competition", "other"):
        for i in c[k]:
            pool.setdefault(i["id"], i)
    items, keys = [], set()
    for i in pool.values():
        if i["id"] in seen_ids or i.get("flow") == "in":
            continue
        if not set(i.get("categories") or []) & DISCRETIONARY:
            continue
        dup_ids = {d.get("id") for d in (i.get("possible_duplicates") or [])}
        if dup_ids & seen_ids:
            continue
        key = (i["government"], round(i.get("max_amount") or 0), i.get("meeting_date"))
        if (i.get("max_amount") or 0) and key in keys:
            continue
        keys.add(key)
        items.append(i)
    rank = {"upcoming": 0, "early_warning": 0, "past_meeting": 1, "undated": 2}
    items.sort(key=lambda i: (rank.get(i.get("stage"), 2),
                              (i.get("days_until_meeting") or 0) if i.get("stage") in ("upcoming", "early_warning") else "",
                              "" if i.get("stage") != "past_meeting" else "".join(chr(255 - ord(ch)) for ch in (i.get("meeting_date") or "")),
                              -(i.get("signal_score") or 0)))
    out = ROOT / "data/sweep"
    out.mkdir(exist_ok=True)
    lanes = [[] for _ in range(LANES)]
    for n, i in enumerate(items):
        text = (i.get("title") or "").strip()
        lanes[n % LANES].append({
            "id": i["id"], "government": i["government"], "body": i.get("body"), "meeting_date": i.get("meeting_date"),
            "stage": i.get("stage"), "days_until_meeting": i.get("days_until_meeting"), "categories": i.get("categories"),
            "amount": i.get("max_amount"), "flow": i.get("flow"), "recipient": i.get("recipient"),
            "link": i.get("link"), "project_id": i.get("project_id"), "project_total": i.get("project_total"),
            "funding_source": i.get("funding_source"), "paying_fund": i.get("paying_fund"),
            "paying_fund_expenditures": i.get("paying_fund_expenditures"), "pct_of_paying_fund": i.get("pct_of_paying_fund"),
            "possible_duplicate_label": i.get("possible_duplicate_label"), "text": text[:1000]})
    for k, lane in enumerate(lanes):
        for n, i in enumerate(lane, 1):
            i["n"] = n
        (out / f"lane_{k + 1}.json").write_text(json.dumps({"lane": k + 1, "count": len(lane), "items": lane}, indent=0))
    st = {}
    for i in items:
        st[i.get("stage")] = st.get(i.get("stage"), 0) + 1
    print(len(items), st, [len(l) for l in lanes], [round((out / f"lane_{k+1}.json").stat().st_size / 1e3) for k in range(LANES)])


if __name__ == "__main__":
    main()
