"""Build the public site's data from the review sheet export.

Inputs
  data/review_export.json   rows exported from the Claude Sheet review queue (Queue and Backlog tabs), one per item,
                            kept up to date by merge_review_patch.py
  site/data/counties.json   city-to-county lookup
  config/committed_projects.json
Outputs
  site/data/items.json      what the page lists
  site/data/projects.json   the committed (approved, mostly unspent) projects list
  site/data/items.csv       the same items as a spreadsheet download
  site/index.html           a plain-HTML snapshot of the list between the STATIC markers, so search engines,
                            AI crawlers and readers without JavaScript see the content (the script replaces it)

Rules
  An item is published when its Decision is Feature or Keep, or, with no Decision yet, when the Suggested call is
  Feature or Keep. Featured = Feature. Statements and news rows are published unless marked Reject.
  Rows flagged in "Needs your review" wait for a Decision. Reject always wins. The reviewer's Note column is never published.
"""
import csv, hashlib, html, io, json, re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CAT_NAMES = {
    # spending: what the money is for
    "outgoing_grant": "Grants to outside groups", "private_benefit": "Private benefit", "facilities": "Buildings & facilities",
    "consultants": "Consultants", "vanity": "Events, art & branding", "officials_perks": "Perks for officials",
    "debt": "Borrowing & debt", "legal": "Legal costs",
    # how it was approved
    "no_bid": "No competitive bidding", "bypass": "No competitive bidding", "bypass_competition": "No competitive bidding",
    "large_spending": "Large dollar amount",
    # money in
    "receipt": "Money coming in",
    # officials' statements
    "deficit projection": "Shortfall warnings", "tax or fee increase": "Tax or fee increases", "tax increase": "Tax or fee increases",
    "service cut": "Service cuts", "amendment 3 impact": "Amendment 3 impact", "amendment 3": "Amendment 3 impact",
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
    lookup = json.loads((ROOT / "site/data/counties.json").read_text())["city_to_county"]
    xp = ROOT / "data/review_export.json"
    if not xp.exists():      # no export yet: keep the current items, refresh everything else
        rows, keep = [], json.loads((ROOT / "site/data/items.json").read_text())
    else:
        rows, keep = json.loads(xp.read_text())["rows"], None
    items, seen = [], set()
    for r in rows:
        decision = (r.get("decision") or "").strip()
        suggested = (r.get("suggested") or "").strip()
        stage = (r.get("stage") or "").strip()
        kind = stage if stage in ("statement", "news") else "spending"
        call = decision or suggested
        if decision == "Reject":
            continue
        if not decision and (r.get("needs_review") or "").strip():
            continue          # flagged for Matt: held off the site until he sets a Decision
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
            "_pick": "reviewer" if decision == "Feature" else ("suggested" if call == "Feature" else None),
            "project_total": num(r.get("project_total")),
            "added": (r.get("added") or None) and str(r["added"])[:10],
        })
    if not keep:
        trim_featured(items)
    out = keep or {"updated": date.today().isoformat(), "items": items}
    items = out["items"]
    (ROOT / "site/data/items.json").write_text(json.dumps(out, indent=1))

    cp = json.loads((ROOT / "config/committed_projects.json").read_text())
    projects = []
    for p in cp.get("projects", []):
        _, cos = counties_for(p.get("government"), lookup)
        projects.append({k: p.get(k) for k in ("id", "government", "project", "total_cost", "annual_payment", "term_years",
                                                  "funding", "votes", "status", "next_decision", "sources", "pinned")} | {"counties": cos})
    projects.sort(key=lambda p: (not p.get("pinned"), -(p.get("total_cost") or 0)))
    (ROOT / "site/data/projects.json").write_text(json.dumps({"updated": out["updated"], "projects": projects}, indent=1))
    write_coverage(lookup)
    write_csv(items)
    write_snapshot(items, projects, out["updated"])
    print(f"site items: {len(items)} ({sum(i['featured'] for i in items)} featured); projects: {len(projects)}")


FEATURED_CAP = 40


def trim_featured(items):
    """Keep Featured short. The reviewer's own Feature picks always stay. Suggested Feature calls fill the remaining
    slots: items still up for a vote first (soonest meeting), then the most recent meetings, larger amounts first."""
    today = date.today().isoformat()
    picks = [i for i in items if i.get("_pick") == "reviewer"]
    sugg = [i for i in items if i.get("_pick") == "suggested"]
    pending = sorted([i for i in sugg if (i.get("meeting_date") or "") >= today], key=lambda i: (i["meeting_date"], -abs(i.get("amount") or 0)))
    past = sorted([i for i in sugg if i not in pending], key=lambda i: (i.get("meeting_date") or "", abs(i.get("amount") or 0)), reverse=True)
    room = max(0, FEATURED_CAP - len(picks))
    chosen = {id(i) for i in picks} | {id(i) for i in (pending + past)[:room]}
    for i in items:
        i["featured"] = id(i) in chosen
        i.pop("_pick", None)


def money(n):
    if n is None:
        return ""
    a = abs(n); sign = "-" if n < 0 else ""
    if a >= 1e9: return f"{sign}${a/1e9:.2f}B".replace(".00B", "B")
    if a >= 1e6: return f"{sign}${a/1e6:.1f}M".replace(".0M", "M")
    return f"{sign}${a:,.0f}"


def write_coverage(lookup):
    """Governments whose agendas are read nightly and have produced items: config sources with archive entries."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import archive_items
    names = {}
    for g in json.loads((ROOT / "config/governments.json").read_text())["governments"]:
        names.setdefault(g["entity_id"], g["name"])
    for k, v in json.loads((ROOT / "config/pdf_sources.json").read_text()).items():
        if k.startswith("_") or not isinstance(v, list):
            continue
        for x in v:
            if isinstance(x, dict) and x.get("entity_id") and not x.get("disabled"):
                names.setdefault(x["entity_id"], x["name"])
    seen = set()
    for f in (ROOT / "data/archive").glob("*.json"):
        seen.update(r.get("entity_id") for r in archive_items.load(str(f)).values())
    by_county = {}
    for eid, name in names.items():
        if eid not in seen:
            continue
        _, cos = counties_for(name, lookup)
        for c in cos:
            by_county.setdefault(c, []).append(name)
    for c in by_county:
        by_county[c] = sorted(set(by_county[c]), key=lambda n: (not n.endswith("County"), n))
    total = sum(1 for e in names if e in seen)
    # Population share: residents of counties whose county government's agendas are read
    # (Duval counts through the consolidated City of Jacksonville). Conservative: covered cities in other counties add more.
    pop = json.loads((ROOT / "site/data/county_population.json").read_text())
    cgov = [c for c, govs in by_county.items() if f"{c} County" in govs or (c == "Duval" and "Jacksonville" in govs)]
    share = round(100 * sum(pop["counties"].get(c, 0) for c in cgov) / pop["florida"])
    (ROOT / "site/data/coverage.json").write_text(json.dumps(
        {"updated": date.today().isoformat(), "governments": total, "county_governments": len(cgov),
         "population_share_county": share, "population_source": pop["source_url"],
         "counties": dict(sorted(by_county.items()))}, indent=1))


def write_csv(items):
    cols = ["government", "counties", "kind", "stage", "meeting_date", "amount", "categories", "description", "shortfall",
            "project_total", "link", "featured", "added"]
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(cols)
    for it in items:
        w.writerow([("; ".join(it[c]) if isinstance(it[c], list) else ("" if it[c] is None else it[c])) for c in cols])
    (ROOT / "site/data/items.csv").write_text(buf.getvalue())


def write_snapshot(items, projects, updated):
    e = html.escape
    def li(it):
        when = f" {e(it['meeting_date'])}" if it.get("meeting_date") else ""
        amt = f" <strong>{e(money(it['amount']))}</strong>" if it.get("amount") is not None else ""
        return (f"<li><b>{e(it['government'] or '')}</b>{when}:{amt} {e(it['description'] or '')} "
                f"<a href=\"{e(it['link'] or '')}\">Source record</a></li>")
    spend = [i for i in items if i["kind"] == "spending"]
    pending = sorted([i for i in spend if i["stage"] in ("upcoming", "early_warning") and (i.get("meeting_date") or "") >= updated],
                     key=lambda i: i["meeting_date"])
    feat = [i for i in spend if i["featured"] and i not in pending]
    rest = [i for i in spend if not i["featured"] and i not in pending]
    parts = [f"<p>Florida local government spending items from public agendas, updated {e(updated)}. Every item links to its public record.</p>"]
    if pending: parts.append("<h2>Up for a vote</h2><ul>" + "".join(li(i) for i in pending) + "</ul>")
    if feat: parts.append("<h2>Featured</h2><ul>" + "".join(li(i) for i in feat[:80]) + "</ul>")
    if projects:
        parts.append("<h2>Big projects</h2><ul>" + "".join(
            f"<li><b>{e(p['government'] or '')}</b>: {e(p['project'] or '')}, {e(money(p.get('total_cost')))}. {e(p.get('status') or '')}</li>"
            for p in projects) + "</ul>")
    if rest: parts.append("<h2>More items</h2><ul>" + "".join(li(i) for i in rest[:150]) + "</ul>")
    page = ROOT / "site/index.html"
    s = page.read_text()
    s = re.sub(r"<!--STATIC-START-->.*?<!--STATIC-END-->", lambda m: "<!--STATIC-START-->" + "".join(parts) + "<!--STATIC-END-->", s, flags=re.S)
    page.write_text(s)


if __name__ == "__main__":
    main()
