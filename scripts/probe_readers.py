"""Probe round 3: BoardDocs item details with money, Clay Swagit event listing, Volusia agenda app pages, Sarasota upcoming."""
import json, re, ssl, urllib.parse, urllib.request
from http.cookiejar import CookieJar

UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public agenda reader)"}
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def get(url, data=None):
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers=UA)
        with op.open(req, timeout=25) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", None) or str(e)[:80], url, ""


def strip(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


print("=== BoardDocs Orange Nov 10 agenda, money items")
s, cid = "fla/orcpsfl", "AA6H5P46CE9C"
st, _, t = get(f"https://go.boarddocs.com/{s}/Board.nsf/BD-GetAgenda?open", {"id": "DNDPQK654DE3", "current_committee_id": cid})
print(st, len(t))
print(t[:1500])
rows = re.findall(r'<li[^>]*class="[^"]*item[^"]*"[^>]*unique="([A-Z0-9]+)"[^>]*>(.*?)</li>', t, re.S)
print("rows", len(rows))
items = re.findall(r'unique="([A-Z0-9]+)"', t)
print("uniques", len(items))
money = [(u, strip(x)[:140]) for u, x in rows if re.search(r"(?i)\$|contract|purchase|award|agreement|approval", x)][:3]
print(money)
for u, _ in money[:2]:
    st4, _, t4 = get(f"https://go.boarddocs.com/{s}/Board.nsf/BD-GetAgendaItem?open", {"id": u, "current_committee_id": cid})
    print("item", st4, strip(t4)[:900])
    print("links", re.findall(r'href="([^"]+)"', t4)[:8])

print("=== Clay Swagit commissioners page")
st, uu, t = get("https://clayfl.new.swagit.com/board-of-commissioners")
ev = re.findall(r'href="(/events/\d+)"[^>]*>(.*?)</a>', t, re.S)[:10]
vids = re.findall(r'href="(/videos/\d+)"[^>]*>(.*?)</a>', t, re.S)[:5]
print(st, [(a, strip(b)[:60]) for a, b in ev], [(a, strip(b)[:60]) for a, b in vids])
print(strip(t)[:600])
st, uu, t = get("https://clayfl.new.swagit.com/events/50593")
body = t[t.find("<body"):]
print("event items", strip(body)[:1500])
print("doc links", [l for l in re.findall(r'href="([^"]+)"', t) if re.search(r"(?i)document|attach|pdf|agenda", l)][:10])

print("=== Volusia agenda list")
st, uu, t = get("https://vcservices.vcgov.org/agenda/agenda-minutes.asp")
sel = re.search(r'<select[^>]*id="AgendaList"[^>]*>(.*?)</select>', t, re.S)
opts = re.findall(r'<option[^>]*value="([^"]+)"[^>]*>(.*?)</option>', sel.group(1) if sel else "")[:6]
print(opts)
if opts:
    v = [o for o in opts if o[0] != "-1"][0][0]
    st, uu, a = get(f"https://vcservices.vcgov.org/agenda/agendas/{v}/agenda.htm")
    print(st, uu, strip(a)[:1200])
    print([l for l in re.findall(r'href="([^"]+)"', a)][:20])

print("=== Sarasota upcoming")
st, uu, t = get("https://sarasota.granicusideas.com/meetings?scope=upcoming")
print([l for l in re.findall(r'href="([^"]+)"', t) if "meetings/" in l][:10])
st, uu, t = get("https://sarasota.granicusideas.com/meetings?scope=past")
print([l for l in re.findall(r'href="([^"]+)"', t) if "meetings/" in l][:10])
