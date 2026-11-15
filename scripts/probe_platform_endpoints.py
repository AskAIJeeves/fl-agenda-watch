"""Round 2: find document URLs on CivicWeb, eScribe, PrimeGov and iQM2 meetings."""
import json, re, urllib.request
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
t0 = (date.today() - timedelta(days=21)).isoformat(); t1 = (date.today() + timedelta(days=21)).isoformat()
def req(url, data=None, ctype=None):
    h = dict(UA); h.update({"Content-Type": ctype} if ctype else {})
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data.encode() if data else None, headers=h), timeout=40)
        return r.status, r.geturl(), r.headers.get("Content-Type", ""), r.read(2000000)
    except urllib.error.HTTPError as e: return e.code, url, "", e.read(2000)
    except Exception as e: return None, url, "", str(e).encode()
def summ(url, b, ct):
    t = b.decode("utf-8", "replace")
    return {"url": url, "ctype": ct, "len": len(b), "pdf": b[:5] == b"%PDF",
            "links": sorted(set(re.findall(r'(?:href|src)=["\']([^"\']*(?:document|Document|FileOpen|filestream|CompiledDocument|Agenda|agenda|Item)[^"\']*)', t)))[:50],
            "text": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))[:800]}
out = {}
# CivicWeb Largo: meetings in window, open a published one
st, fu, ct, b = req(f"https://largo.civicweb.net/Services/MeetingsService.svc/meetings?from={t0}&to={t1}")
ms = json.loads(b); pub = [m for m in ms if m.get("Published")]
out["civicweb_meetings"] = [(m["Id"], m["Name"], m["Published"]) for m in ms]
if pub:
    m = pub[0]; u = f"https://largo.civicweb.net/Portal/MeetingInformation.aspx?Id={m['Id']}"
    st, fu, ct, b = req(u); out["civicweb_meeting"] = summ(u, b, ct)
    docs = re.findall(r'(/document/\d+[^"\']*)', b.decode("utf-8", "replace"))
    if docs:
        u2 = "https://largo.civicweb.net" + docs[0].replace("&amp;", "&"); st, fu, ct, b2 = req(u2); out["civicweb_doc"] = summ(u2, b2, ct)
# eScribe Orlando
st, fu, ct, b = req("https://pub-orlando.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings", json.dumps({"calendarStartDate": t0, "calendarEndDate": t1}), "application/json; charset=utf-8")
d = json.loads(b)["d"]; out["escribe_meeting_keys"] = list(d[0].keys()) if d else []
out["escribe_sample"] = d[:2]
if d:
    m = [x for x in d if "Council" in x["MeetingName"]][0] if any("Council" in x["MeetingName"] for x in d) else d[0]
    st, fu, ct, b = req(m["Url"]); out["escribe_meeting"] = summ(m["Url"], b, ct)
    for lk in re.findall(r'href=["\']([^"\']*(?:FileStream|filestream)[^"\']*)', b.decode("utf-8", "replace"))[:1]:
        u2 = lk if lk.startswith("http") else "https://pub-orlando.escribemeetings.com/" + lk.lstrip("/")
        st, fu, ct, b2 = req(u2.replace("&amp;", "&")); out["escribe_doc"] = summ(u2, b2, ct)
# PrimeGov Miami Beach
st, fu, ct, b = req("https://miamibeachfl.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings")
d = json.loads(b); out["primegov_sample"] = d[:1]
if d:
    for doc in d[0]["documentList"][:4]:
        for u in [f"https://miamibeachfl.primegov.com/Portal/Meeting?meetingTemplateId={doc['templateId']}",
                  f"https://miamibeachfl.primegov.com/Public/CompiledDocument?meetingTemplateId={doc['templateId']}&compileOutputType={doc['compileOutputType']}"]:
            st, fu, ct, b2 = req(u); out.setdefault("primegov_docs", []).append({**summ(u, b2, ct), "templateName": doc["templateName"], "status": st})
# iQM2 Miami
st, fu, ct, b = req("https://miamifl.iqm2.com/Citizens/Detail_Meeting.aspx?ID=4155"); out["iqm2_meeting"] = summ("Detail_Meeting 4155", b, ct)
for lk in re.findall(r'href=["\']([^"\']*FileOpen[^"\']*)', b.decode("utf-8", "replace"))[:2]:
    u2 = "https://miamifl.iqm2.com/Citizens/" + lk.split("/Citizens/")[-1].lstrip("/").replace("&amp;", "&")
    st, fu, ct, b2 = req(u2); out.setdefault("iqm2_docs", []).append(summ(u2, b2, ct))
(ROOT / "data/endpoint_probe.json").write_text(json.dumps(out, indent=1, default=str))
