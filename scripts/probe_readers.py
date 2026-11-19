"""Probe new reader targets from GitHub's servers and print what each endpoint returns.

Targets: BoardDocs school districts, Swagit (Clay County), Volusia County Council action lists and agenda pages,
City of Sarasota (granicusideas). Read-only GETs/POSTs to public pages; stops at any block or error.
"""
import json, re, ssl, urllib.parse, urllib.request
from http.cookiejar import CookieJar

UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public agenda reader)"}
ctx = ssl.create_default_context()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()), urllib.request.HTTPSHandler(context=ctx))


def get(url, data=None, n=400):
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers=UA)
        with op.open(req, timeout=25) as r:
            b = r.read()
            return r.status, r.geturl(), b.decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", None) or str(e)[:80], url, ""


print("=== BoardDocs")
slugs = ["fla/orcpsfl", "fl/orcpsfl", "fl/pcsb", "fl/pinellas", "fl/hcps", "fl/hcpsfl", "fl/pasco", "fl/pascoschools", "fl/palmbeach",
         "fl/pbcsd", "fl/broward", "fl/browardschools", "fl/dcps", "fl/duval", "fl/polk", "fl/polkschools", "fl/lee", "fl/leeschools",
         "fl/brevco", "fl/brevard", "fl/vcsfl", "fl/volusia", "fl/scps", "fl/seminole", "fl/osceola", "fl/sarasota", "fl/manatee",
         "fl/collier", "fl/ccps", "fl/marion", "fl/lake", "fl/lcsfl", "fl/sjcsd", "fl/stjohns", "fl/alachua", "fl/sbac", "fl/leon",
         "fl/escambia", "fl/ecsd", "fl/okaloosa", "fl/santarosa", "fl/clay", "fl/flagler", "fl/charlotte", "fl/hernando", "fl/citrus",
         "fl/stlucie", "fl/martin", "fl/ircsd", "fl/bay", "fl/monroe", "fl/nassau", "fl/highlands", "fl/sumter", "fl/putnam", "fl/walton"]
for s in slugs:
    st, u, t = get(f"https://go.boarddocs.com/{s}/Board.nsf/Public")
    cid = re.findall(r'current_committee_id"?\s*[:=]\s*"?([A-Z0-9]{8,})', t) or re.findall(r'committee[_-]?id[^A-Z0-9]{1,6}([A-Z0-9]{12,})', t, re.I)
    title = re.findall(r"<title>([^<]*)", t)
    print(s, st, (title[0][:60] if title else ""), cid[:1])

print("=== BoardDocs meeting list (first working slug)")
for s in slugs:
    st, u, t = get(f"https://go.boarddocs.com/{s}/Board.nsf/Public")
    cid = re.findall(r'current_committee_id"?\s*[:=]\s*"?([A-Z0-9]{8,})', t)
    if st == 200 and cid:
        st2, _, t2 = get(f"https://go.boarddocs.com/{s}/Board.nsf/BD-GetMeetingsList?open", {"current_committee_id": cid[0]})
        print(s, st2, t2[:600])
        try:
            ms = json.loads(t2)
            m = ms[0] if ms else None
            if m:
                uid = m.get("unique") or m.get("id")
                st3, _, t3 = get(f"https://go.boarddocs.com/{s}/Board.nsf/BD-GetAgenda?open", {"id": uid, "current_committee_id": cid[0]})
                print("agenda", st3, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t3))[:800])
        except Exception as e:
            print("parse", e)
        break

print("=== Swagit Clay")
for u in ["https://clayfl.new.swagit.com/", "https://clayfl.new.swagit.com/views/", "https://clayfl.new.swagit.com/events/48611",
          "https://clayfl.new.swagit.com/videos/237315"]:
    st, uu, t = get(u)
    ev = sorted(set(re.findall(r'/events/(\d+)', t)))[-8:]
    vids = sorted(set(re.findall(r'/videos/(\d+)', t)))[-5:]
    docs = re.findall(r'href="([^"]+(?:\.pdf|/document[^"]*|/agenda[^"]*|attachments?[^"]*))"', t, re.I)[:8]
    print(u, st, "events", ev, "videos", vids, "docs", docs, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:300])

print("=== Volusia")
for u in ["https://www.volusia.org/government/county-council/county-council-meetings/",
          "https://www.volusia.org/government/county-council/county-council-meetings/actions.stml",
          "https://www.volusia.org/government/county-council/county-council-meetings/agendas.stml",
          "https://www.volusia.org/government/county-council/county-council-meetings/minutes.stml"]:
    st, uu, t = get(u)
    pdfs = re.findall(r'href="([^"]+\.pdf[^"]*)"', t, re.I)[:10]
    links = [l for l in re.findall(r'href="([^"]+)"', t) if re.search(r"(?i)agenda|action|minutes|meeting", l)][:15]
    print(u, st, uu, "pdfs", pdfs, "links", links)

print("=== Sarasota city")
for u in ["https://sarasota.granicusideas.com/meetings", "https://sarasotafl.granicusideas.com/meetings",
          "https://www.sarasotafl.gov/government/city-commission/agendas-minutes"]:
    st, uu, t = get(u)
    mt = re.findall(r'href="(/meetings/[^"]+)"', t)[:8]
    print(u, st, uu, mt, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:200])
