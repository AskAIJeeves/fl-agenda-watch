"""Build the public site's data from the review sheet export.

Inputs
  data/review_export.json   rows exported from the Claude Sheet review queue (Queue and Backlog tabs), one per item,
                            kept up to date by merge_review_patch.py
  site/data/counties.json   city-to-county lookup
  config/committed_projects.json
Outputs
  site/data/items.json      what the page lists
  site/data/projects.json   the committed (approved, mostly unspent) projects list

Rules
  An item is published when its Decision is Feature or Keep, or, with no Decision yet, when the Suggested call is
  Feature or Keep. Featured = Feature. Statements and news rows are published unless marked Reject.
  Reject always wins. The reviewer's Note column is never published.
"""
import hashlib, json, re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CAT_NAMES = {
    "outgoing_grant": "Grant to outside group", "no_bid": "No-bid / bidding waived", "vanity": "Vanity & events",
    "officials_perks": "Officials' perks", "private_benefit": "Private benefit", "facilities": "Facilities",
    "consultants": "Consultants", "debt": "Debt", "legal": "Legal", "large_spending": "Large spending",
    "receipt": "Money received", "deficit projection": "Deficit projection", "tax or fee increase": "Tax or fee increase",
    "service cut": "Service cut", "amendment 3 impact": "Amendment 3", "amendment 3": "Amendment 3",
}
SPLIT = re.compile(r"\s*(?:/|;|,| and )\s*")


def counties_for(gov, lookup):
    out, govs = [], [g for g in SPLIT.split(gov or "") if g]
    for g in govs:
        g2 = re.sub(r"^(City|Town|Village) of\s+", "", g).strip()
        if g2.lower().endswith(" county"):
            c = g2[:-7].strip()
        else:
            c = lookup.get(g2) or lookup.get(g2.replace("St.", "Saint")) or lookup.get(g2.replace("Saint", "St."))
        if c and c not in out:
            out.append(c)
    return govs, out or ["Other"]


def categories(raw):
    cats = []
    for part in re.split(r"[;,]", raw or ""):
        k = part.strip().lower()
        if not k:
            continue
        name = CAT_NAMES.get(k, part.strip()[:1].upper() + part.strip()[1:])
        if name not in cats:
            cats.append(name)
    return cats


def num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def main():
    rows = json.loads((ROOT / "data/review_export.json").read_text())["rows"]
    lookup = json.loads((ROOT / "site/data/counties.json").read_text())["city_to_county"]
    items, seen = [], set()
    for r in rows:
        decision = (r.get("decision") or "").strip()
        suggested = (r.get("suggested") or "").strip()
        stage = (r.get("stage") or "").strip()
        kind = stage if stage in ("statement", "news") else "spending"
        call = decision or suggested
        if decision == "Reject":
            continue
        if kind == "spending" and call not in ("Feature", "Keep"):
            continue
        iid = r.get("item_id") or r.get("link")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        govs, cos = counties_for(r.get("government"), lookup)
        items.append({
            "id": hashlib.sha1(iid.encode()).hexdigest()[:10],
            "government": r.get("government"),
            "governments": govs,
            "level": "county" if all(g.lower().endswith("county") for g in govs) else "city",
            "counties": cos,
            "description": r.get("description"),
            "shortfall": r.get("shortfall") or None,
            "amount": num(r.get("amount")),
            "link": r.get("link"),
            "stage": stage or "undated",
            "kind": kind,
            "meeting_date": (r.get("meeting_date") or None) and str(r["meeting_date"])[:10],
            "categories": categories(r.get("category")),
            "featured": call == "Feature",
            "project_total": num(r.get("project_total")),
            "added": (r.get("added") or None) and str(r["added"])[:10],
        })
    out = {"updated": date.today().isoformat(), "items": items}
    (ROOT / "site/data/items.json").write_text(json.dumps(out, indent=1))

    cp = json.loads((ROOT / "config/committed_projects.json").read_text())
    projects = []
    for p in cp.get("projects", []):
        _, cos = counties_for(p.get("government"), lookup)
        projects.append({k: p.get(k) for k in ("id", "government", "project", "total_cost", "annual_payment", "term_years",
                                                  "funding", "votes", "status", "next_decision", "sources", "pinned")} | {"counties": cos})
    projects.sort(key=lambda p: (not p.get("pinned"), -(p.get("total_cost") or 0)))
    (ROOT / "site/data/projects.json").write_text(json.dumps({"updated": out["updated"], "projects": projects}, indent=1))
    print(f"site items: {len(items)} ({sum(i['featured'] for i in items)} featured); projects: {len(projects)}")


if __name__ == "__main__":
    main()
