"""Save an eScribe meeting page and test FileStream access variants; retry iQM2."""
import json, re, urllib.request, http.cookiejar
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
out = {}
host = "pub-capecoral.escribemeetings.com"
t0 = (date.today() - timedelta(days=14)).isoformat(); t1 = (date.today() + timedelta(days=21)).isoformat()
jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ms = json.loads(op.open(urllib.request.Request(f"https://{host}/MeetingsCalendarView.aspx/GetCalendarMeetings", data=json.dumps({"calendarStartDate": t0, "calendarEndDate": t1}).encode(), headers={**UA, "Content-Type": "application/json; charset=utf-8"}), timeout=60).read())["d"]
m = [x for x in ms if "Regular" in x["MeetingName"] and x.get("HasAgenda")][0]
out["meeting"] = {k: m[k] for k in ("ID", "MeetingName", "StartDate", "Url", "MeetingDocumentLink")}
mu = f"https://{host}/Meeting.aspx?Id={m['ID']}&Agenda=Agenda&lang=English"
page = op.open(urllib.request.Request(mu, headers=UA), timeout=60).read()
(ROOT / "data/escribe_sample.html").write_bytes(page)
out["cookies"] = [c.name for c in jar]
fs = re.findall(rb'(FileStream\.ashx\?DocumentId=\d+)', page)[:2]
out["tests"] = []
for f in fs:
    for variant in [f"https://{host}/{f.decode()}", f"https://{host}/filestream.ashx?DocumentId={f.decode().split('=')[1]}"]:
        for hdr in [{**UA, "Referer": mu}, {**UA, "Referer": mu, "Accept": "application/pdf,*/*"}]:
            try:
                r = op.open(urllib.request.Request(variant, headers=hdr), timeout=60); b = r.read(2000)
                out["tests"].append([variant, list(hdr)[-1], r.status, b[:8].decode("latin1")])
            except urllib.error.HTTPError as e:
                out["tests"].append([variant, list(hdr)[-1], e.code, e.read(300).decode("utf-8", "replace")[:200]])
try:
    r = urllib.request.urlopen(urllib.request.Request("https://miamifl.iqm2.com/Citizens/Default.aspx", headers=UA), timeout=120)
    out["iqm2"] = [r.status, len(r.read())]
except Exception as e:
    out["iqm2"] = str(e)
(ROOT / "data/endpoint_probe.json").write_text(json.dumps(out, indent=1))
