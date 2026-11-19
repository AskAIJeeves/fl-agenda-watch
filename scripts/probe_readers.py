"""Probe round 2: BoardDocs API shape, Volusia agenda app, Clay Swagit event list, Sarasota granicusideas links."""
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


print("=== BoardDocs page")
st, u, t = get("https://go.boarddocs.com/fl/pasco/Board.nsf/Public")
for m in re.finditer(r"(?i)committee", t):
    print("...", t[max(0, m.start() - 120):m.start() + 160].replace("\n", " "))
    if m.start() > 60000: break
ids = re.findall(r'"([A-Z0-9]{12})"', t)
print("12-char ids", sorted(set(ids))[:20])
for s in ["fl/pasco", "fla/orcpsfl", "fl/palmbeach"]:
    st, u, t = get(f"https://go.boarddocs.com/{s}/Board.nsf/Public")
    cands = sorted(set(re.findall(r'id="committee[^"]*"[^>]*value="([A-Z0-9]+)"', t) + re.findall(r'current_committee_id[^A-Z0-9]{0,8}([A-Z0-9]{12})', t)
                       + re.findall(r'committeeid[^A-Z0-9]{0,8}([A-Z0-9]{12})', t, re.I)))
    print(s, "candidates", cands)
    for cid in cands[:3]:
        st2, _, t2 = get(f"https://go.boarddocs.com/{s}/Board.nsf/BD-GetMeetingsList?open", {"current_committee_id": cid})
        print(" list", cid, st2, len(t2), t2[:300])
        try:
            ms = json.loads(t2)
        except Exception:
            continue
        if ms:
            ms = sorted(ms, key=lambda m: m.get("numberdate", ""), reverse=True)
            print(" newest", ms[:3])
            uid = ms[0].get("unique")
            st3, _, t3 = get(f"https://go.boarddocs.com/{s}/Board.nsf/BD-GetAgenda?open", {"id": uid, "current_committee_id": cid})
            print(" agenda", st3, len(t3), strip(t3)[:700])
            items = re.findall(r'unique="([A-Z0-9]+)"', t3)[:3] or re.findall(r"id=['\"]([A-Z0-9]{12})['\"]", t3)[:3]
            print(" item ids", items)
            for it in items[:2]:
                st4, _, t4 = get(f"https://go.boarddocs.com/{s}/Board.nsf/BD-GetAgendaItem?open", {"id": it, "current_committee_id": cid})
                print(" item", st4, len(t4), strip(t4)[:500], re.findall(r'href="([^"]+)"', t4)[:5])
            break
    print()

print("=== Volusia agenda app")
for u in ["https://vcservices.vcgov.org/agenda/agenda-minutes.asp"]:
    st, uu, t = get(u)
    print(u, st, uu, strip(t)[:600])
    print([l for l in re.findall(r'(?:href|action)="([^"]+)"', t)][:30])
    print(re.findall(r'<form[^>]*>', t)[:3], re.findall(r'<(?:input|select)[^>]*name="([^"]+)"', t)[:20])

print("=== Clay Swagit home links")
st, uu, t = get("https://clayfl.new.swagit.com/")
print(sorted(set(re.findall(r'href="([^"#]+)"', t)))[:60])
st, uu, t = get("https://clayfl.new.swagit.com/events/50593")
print("event", st, strip(t)[:900])
print(sorted(set(re.findall(r'href="([^"#]+)"', t)))[:40])

print("=== Sarasota granicusideas")
st, uu, t = get("https://sarasota.granicusideas.com/meetings")
print(sorted(set(re.findall(r'href="([^"#]+)"', t)))[:60])
print(strip(t)[200:1200])
