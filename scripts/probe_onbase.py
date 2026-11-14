"""Explore OnBase Agenda Online endpoints for Tampa and Osceola. Writes data/onbase_probe.json."""
import json, re, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "X-Requested-With": "XMLHttpRequest"}
BASES = ["https://tampagov.hylandcloud.com/251agendaonline", "https://docs.osceola.org/OnBaseAgendaOnline"]
PATHS = ["/", "/Meetings", "/Meetings/Search?dropid=4&mtids=", "/Meetings/Search?dropid=11", "/Meetings/Search?dropid=1",
         "/Meetings/Search?dropsv=&dropid=4&mtids=&dateRange=", "/Meetings/ViewMeeting?id=1000&doctype=1",
         "/Meetings/Upcoming", "/Meetings/Recent", "/Meetings/GetMeetings", "/Search?term="]
out = {}
for b in BASES:
    res = []
    for p in PATHS:
        u = b + p
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
                body = r.read(400000).decode("utf-8", "replace"); st = r.status; fu = r.geturl()
        except urllib.error.HTTPError as e:
            body, st, fu = e.read(3000).decode("utf-8", "replace"), e.code, u
        except Exception as e:
            body, st, fu = str(e), None, u
        links = sorted(set(re.findall(r'(?:href|src|data-url|action)=["\']([^"\']+)', body)))[:80]
        scripts = re.findall(r"(?:url|ajax|fetch)\s*[:(]\s*['\"]([^'\"]+)", body)[:30]
        res.append({"url": u, "final": fu, "status": st, "len": len(body), "head": body[:600], "links": links, "script_urls": scripts,
                    "ids": sorted(set(re.findall(r"(?:id|meetingId|MeetingId)=(\d{2,6})", body)))[-20:]})
    out[b] = res
(ROOT / "data/onbase_probe.json").write_text(json.dumps(out, indent=1))
