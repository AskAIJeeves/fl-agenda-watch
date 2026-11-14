"""Find each government's agenda platform by reading its own website: the homepage plus
pages linked as agendas/meetings, harvesting links to known agenda platforms."""
import json, re, sys, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
PLAT = re.compile(r"https?://[a-z0-9.-]*(granicus\.com|legistar\.com|iqm2\.com|civicclerk\.com|primegov\.com|novusagenda\.com|boarddocs\.com|escribemeetings\.com|hylandcloud\.com|civicweb\.net|meetings\.municode\.com|municodemeetings\.com|agendalink|swagit\.com|destinyhosted\.com|suiteonemedia\.com|boardsync|accessgov|diligent\.community|onbaseonline|agendaquick|ompnetwork|youtube\.com/@)[^\s\"'<>]*", re.I)
NAV = re.compile(r"(?i)agenda|meeting|minutes|commission|council|board of county")

def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            return r.geturl(), r.read(600000).decode("utf-8", "replace")
    except Exception as e:
        return url, ""

def hrefs(base, html):
    return [urllib.parse.urljoin(base, h) for h in re.findall(r'href=["\']([^"\'#]+)', html, re.I)]

def scan(g):
    found, pages = {}, []
    for dom in g["domains"]:
        u, html = get(f"https://{dom}/")
        if not html: continue
        pages.append(u)
        for m in PLAT.finditer(html): found.setdefault(m.group(1).lower(), set()).add(m.group(0)[:160])
        host = urllib.parse.urlparse(u).netloc
        nav = []
        for h in hrefs(u, html):
            if NAV.search(h) and (urllib.parse.urlparse(h).netloc in (host, "") or PLAT.search(h)):
                nav.append(h)
        for h in list(dict.fromkeys(nav))[:12]:
            if PLAT.search(h):
                found.setdefault(PLAT.search(h).group(1).lower(), set()).add(h[:160]); continue
            u2, h2 = get(h); pages.append(u2)
            if "AgendaCenter" in u2 and "ViewFile" in h2: found.setdefault("civicplus_agendacenter", set()).add(u2)
            for m in PLAT.finditer(h2): found.setdefault(m.group(1).lower(), set()).add(m.group(0)[:160])
        if found: break
    found.pop("youtube.com/@", None)
    return {**g, "pages_read": len(pages), "platforms": {k: sorted(v)[:6] for k, v in found.items()}}

def main():
    cfg = json.loads((ROOT / "config/probe_sites.json").read_text())
    with ThreadPoolExecutor(8) as ex: res = list(ex.map(scan, cfg["governments"]))
    (ROOT / "data/probe_sites.json").write_text(json.dumps(res, indent=1))
    for r in res: print(r["name"], r["pages_read"], list(r["platforms"]), file=sys.stderr)

if __name__ == "__main__":
    main()
