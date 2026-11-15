"""Explore endpoints for CivicWeb, eScribe, PrimeGov and iQM2. Writes data/endpoint_probe.json."""
import json, re, urllib.request
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
t0 = (date.today() - timedelta(days=10)).isoformat(); t1 = (date.today() + timedelta(days=30)).isoformat()

def req(url, data=None, ctype=None):
    h = dict(UA)
    if ctype: h["Content-Type"] = ctype
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=data.encode() if data else None, headers=h), timeout=30)
        b = r.read(300000); return r.status, r.geturl(), r.headers.get("Content-Type", ""), b
    except urllib.error.HTTPError as e:
        return e.code, url, "", e.read(2000)
    except Exception as e:
        return None, url, "", str(e).encode()

TESTS = {
 "civicweb_largo": [("https://largo.civicweb.net/Services/MeetingsService.svc/meetings?from=%s&to=%s" % (t0, t1), None, None),
                    ("https://largo.civicweb.net/Portal/MeetingSchedule.aspx", None, None),
                    ("https://largo.civicweb.net/Portal/MeetingTypeList.aspx", None, None),
                    ("https://largo.civicweb.net/Portal/", None, None)],
 "civicweb_pasco": [("https://pasco.civicweb.net/Services/MeetingsService.svc/meetings?from=%s&to=%s" % (t0, t1), None, None),
                    ("https://pasco.civicweb.net/Portal/MeetingTypeList.aspx", None, None)],
 "escribe_orlando": [("https://pub-orlando.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings", json.dumps({"calendarStartDate": t0, "calendarEndDate": t1}), "application/json; charset=utf-8"),
                     ("https://pub-orlando.escribemeetings.com/", None, None)],
 "primegov_miamibeach": [("https://miamibeachfl.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings", None, None),
                         ("https://miamibeachfl.primegov.com/api/v2/PublicPortal/ListArchivedMeetings?year=2026", None, None)],
 "iqm2_miami": [("https://miamifl.iqm2.com/Services/RSS.aspx?Feed=Calendar", None, None),
                ("https://miamifl.iqm2.com/Citizens/Calendar.aspx", None, None),
                ("https://miamifl.iqm2.com/Citizens/Default.aspx", None, None)],
}
out = {}
for k, tests in TESTS.items():
    out[k] = []
    for url, data, ct in tests:
        st, fu, ctype, b = req(url, data, ct)
        txt = b.decode("utf-8", "replace")
        out[k].append({"url": url, "status": st, "final": fu, "ctype": ctype, "len": len(b), "head": txt[:1500],
                       "links": sorted(set(re.findall(r'(?:href|src)=["\']([^"\']*(?:Meeting|document|Document|FileOpen|filestream|Detail_Meeting|CompiledDocument|Agenda)[^"\']*)', txt)))[:40]})
(ROOT / "data/endpoint_probe.json").write_text(json.dumps(out, indent=1))
