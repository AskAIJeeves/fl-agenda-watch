"""Discovery probe: find uncovered Florida cities and counties on the agenda
platforms the project already reads (Legistar, CivicClerk, PrimeGov,
eScribe, iQM2, Municode Meetings) by trying likely tenant names.
Writes data/platform_probe.json. Governments already configured are skipped.
"""
import concurrent.futures as cf
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from probe_granicus import CITIES, COUNTIES, slug  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public agenda research)", "Accept": "application/json, text/html"}


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10) as r:
            return r.status, r.read(200000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, str(e)[:100]


def names(name, county):
    b = slug(name)
    if county:
        return {"base": [f"{b}county", f"{b}countyfl", f"{b}fl", f"{b}co", f"{b}cofl", f"{b}bocc", f"my{b}", b],
                "fl": [f"{b}cofl", f"{b}countyfl", f"{b}county", f"{b}fl"]}
    return {"base": [b, f"{b}fl", f"cityof{b}", f"cityof{b}fl", f"{b}florida", f"{b}gov", f"my{b}"],
            "fl": [f"{b}fl", f"cityof{b}fl", b, f"cityof{b}"]}


def check(name, county):
    n, hits = names(name, county), []
    for c in n["base"]:                                           # Legistar web API
        st, body = get(f"https://webapi.legistar.com/v1/{c}/bodies")
        if st == 200 and body.strip().startswith("["):
            hits.append({"platform": "legistar", "client": c, "bodies": body.count("BodyId")})
            break
    for t in n["fl"]:                                             # CivicClerk
        st, body = get(f"https://{t}.api.civicclerk.com/v1/Events?$top=1")
        if st == 200 and '"value"' in body:
            hits.append({"platform": "civicclerk", "tenant": t})
            break
    for h in n["base"][:5]:                                       # Granicus (agenda RSS)
        for vid in (1, 2, 3):
            st, body = get(f"https://{h}.granicus.com/ViewPublisherRSS.php?view_id={vid}&mode=agendas")
            if st == 200 and body.count("<item>") > 3 and ("FL" in body[:3000] or "Florida" in body[:3000]):
                hits.append({"platform": "granicus", "host": f"{h}.granicus.com", "view_id": vid, "items": body.count("<item>")})
                break
        if hits and hits[-1]["platform"] == "granicus":
            break
    for h in n["base"][:3] + n["fl"][:1]:                         # PrimeGov
        st, body = get(f"https://{h}.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings")
        if st == 200 and body.strip().startswith("["):
            hits.append({"platform": "primegov", "host": f"{h}.primegov.com"})
            break
    for h in n["base"][:3]:                                       # eScribe
        st, body = get(f"https://pub-{h}.escribemeetings.com/")
        if st == 200 and "escribe" in body.lower():
            hits.append({"platform": "escribe", "host": f"pub-{h}.escribemeetings.com"})
            break
    for h in n["fl"][:2] + n["base"][:1]:                         # iQM2
        st, body = get(f"https://{h}.iqm2.com/Citizens/Default.aspx")
        if st == 200 and "iqm2" in body.lower():
            hits.append({"platform": "iqm2", "host": f"{h}.iqm2.com"})
            break
    b = slug(name)
    for h in ([f"{b}county-fl", f"{b}-fl"] if county else [f"{b}-fl", f"cityof{b}-fl"]):   # Municode Meetings
        st, body = get(f"https://{h}.municodemeetings.com/")
        if st == 200 and "municode" in body.lower():
            hits.append({"platform": "municode_meetings", "host": f"{h}.municodemeetings.com"})
            break
    return {"name": name + (" County" if county else ""), "hits": hits}


def covered():
    g = json.loads((ROOT / "config/governments.json").read_text())["governments"]
    p = json.loads((ROOT / "config/pdf_sources.json").read_text())
    out = {slug(x["name"]) for x in g}
    for k, v in p.items():
        if isinstance(v, list):
            out |= {slug(x.get("name", "")) for x in v if isinstance(x, dict)}
    return out


TARGETS = [("Brevard", True), ("Volusia", True), ("Marion", True), ("Leon", True), ("Clay", True), ("DeSoto", True),
           ("Manatee", True), ("Hialeah", False), ("West Palm Beach", False), ("Palm Bay", False), ("Pompano Beach", False),
           ("Fort Myers", False), ("Lauderhill", False), ("Sarasota", False), ("Panama City", False), ("Naples", False),
           ("Homestead", False), ("DeLand", False), ("Temple Terrace", False), ("Miami Gardens", False), ("Largo", False)]


def main():
    import os
    if os.environ.get("TARGETED"):
        res = [check(n, c) for n, c in TARGETS]
        (ROOT / "data/platform_probe_targeted.json").write_text(json.dumps(res, indent=1))
        for r in res:
            print(r["name"], r["hits"])
        return
    have = covered()
    cands = [(c.strip(), False) for c in CITIES.split(",") if c.strip()] + \
            [(c.strip(), True) for c in COUNTIES.split(",") if c.strip()]
    cands = [(n, c) for n, c in cands if slug(n + (" County" if c else "")) not in have]
    with cf.ThreadPoolExecutor(24) as ex:
        res = list(ex.map(lambda a: check(*a), cands))
    found = [r for r in res if r["hits"]]
    (ROOT / "data/platform_probe.json").write_text(json.dumps(
        {"checked": len(res), "found": len(found), "results": found,
         "not_found": [r["name"] for r in res if not r["hits"]]}, indent=1))
    print(f"checked {len(res)} uncovered governments; platforms found for {len(found)}")
    for r in found:
        print(r["name"], r["hits"])


if __name__ == "__main__":
    main()
