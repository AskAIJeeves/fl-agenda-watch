"""Test which agenda platform each government uses. Writes data/probe_results.json."""
import json, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public records research)"}

def get(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.geturl(), r.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, ""
    except Exception as e:
        return None, url, str(e)[:100]

CHECKS = {
 "legistar":   (lambda s: f"https://webapi.legistar.com/v1/{s}/bodies?$top=1", lambda st, u, b: st == 200 and b.strip().startswith("[") and "BodyId" in b),
 "granicus":   (lambda s: f"https://{s}.granicus.com/ViewPublisher.php?view_id=1", lambda st, u, b: st == 200 and ("granicus" in b.lower()) and ("AgendaViewer" in b or "MediaPlayer" in b or "listingTable" in b)),
 "granicus_v2":(lambda s: f"https://{s}.granicus.com/ViewPublisher.php?view_id=2", lambda st, u, b: st == 200 and ("AgendaViewer" in b or "MediaPlayer" in b)),
 "granicus_v3":(lambda s: f"https://{s}.granicus.com/ViewPublisher.php?view_id=3", lambda st, u, b: st == 200 and ("AgendaViewer" in b or "MediaPlayer" in b)),
 "iqm2":       (lambda s: f"https://{s}.iqm2.com/Citizens/Default.aspx", lambda st, u, b: st == 200 and "iqm2" in u.lower() and "Meeting" in b),
 "civicclerk": (lambda s: f"https://{s}.api.civicclerk.com/v1/Events?$top=1", lambda st, u, b: st == 200 and '"value"' in b),
 "primegov":   (lambda s: f"https://{s}.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings", lambda st, u, b: st == 200 and b.strip().startswith("[") and len(b.strip()) > 2),
 "boarddocs":  (lambda s: f"https://go.boarddocs.com/fl/{s}/Board.nsf/Public", lambda st, u, b: st == 200 and "BoardDocs" in b and "not found" not in b.lower()),
 "civicweb":   (lambda s: f"https://{s}.civicweb.net/Portal/", lambda st, u, b: st == 200 and "civicweb" in u.lower() and "Portal" in b),
 "onbase":     (lambda s: f"https://{s}.hylandcloud.com/", lambda st, u, b: st in (200, 403) and "hylandcloud" in u),
 "escribe":    (lambda s: f"https://pub-{s}.escribemeetings.com/", lambda st, u, b: st == 200 and "escribe" in b.lower() and "Meeting" in b),
}

def probe(g):
    hits, tried = [], 0
    for s in g["slugs"]:
        for plat, (mk, ok) in CHECKS.items():
            url = mk(s); st, final, body = get(url); tried += 1
            if ok(st, final, body): hits.append({"platform": plat, "slug": s, "url": url})
    for dom in g.get("domains", []):
        st, final, body = get(f"https://{dom}/AgendaCenter")
        if st == 200 and "AgendaCenter" in body: hits.append({"platform": "civicplus_agendacenter", "url": f"https://{dom}/AgendaCenter"})
        st, final, body = get(f"https://{dom}/")
        found = sorted(set(re.findall(r"https?://[a-z0-9.-]*(?:granicus|legistar|iqm2|civicclerk|primegov|novusagenda|boarddocs|escribemeetings|hylandcloud|municode|civicweb|agendalink|swagit)[a-z0-9./?=_&-]*", body, re.I)))[:15]
        if found: hits.append({"platform": "homepage_links", "url": f"https://{dom}/", "links": found})
    return {**g, "hits": hits, "checks": tried}

def main():
    cfg = json.loads((ROOT / "config/probe_list.json").read_text())
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(probe, cfg["governments"]))
    (ROOT / "data/probe_results.json").write_text(json.dumps(res, indent=1))
    for r in res: print(r["name"], [h["platform"] + ":" + h.get("slug", "") for h in r["hits"]], file=sys.stderr)

if __name__ == "__main__":
    main()
