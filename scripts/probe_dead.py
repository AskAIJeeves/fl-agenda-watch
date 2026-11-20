"""Probe candidate agenda sources for readers that produce nothing (list from the research brief).
Runs on a GitHub runner; records HTTP status, size, bot-challenge markers and a snippet per URL.
Writes data/probe_dead.json. Polite: one request per URL, 2 s apart, no retries, no evasion."""
import json, time, urllib.request, urllib.error, re
from datetime import datetime, timezone
UA = {"User-Agent": "Mozilla/5.0 (compatible; floridaspending.com agenda reader; +https://floridaspending.com)"}
CH = re.compile(r"(?i)cf-chl|just a moment|captcha|verify you are human|attention required|access denied")
Y = "2026"
T = {
 # Legistar API (we already read Legistar this way for others)
 "legistar:martin": "https://webapi.legistar.com/v1/martin/events?$top=3&$orderby=EventDate%20desc",
 "legistar:hernandocountyfl": "https://webapi.legistar.com/v1/hernandocountyfl/events?$top=3&$orderby=EventDate%20desc",
 "legistar:coralgables": "https://webapi.legistar.com/v1/coralgables/events?$top=3&$orderby=EventDate%20desc",
 "legistar:margatefl": "https://webapi.legistar.com/v1/margatefl/events?$top=3&$orderby=EventDate%20desc",
 "legistar:hallandalebeach": "https://webapi.legistar.com/v1/hallandalebeach/events?$top=3&$orderby=EventDate%20desc",
 "legistar-web:martin": "https://martin.legistar.com/Calendar.aspx",
 # iQM2
 "iqm2:okaloosa rss": "https://okaloosacountyfl.iqm2.com/Services/RSS.aspx?Feed=Calendar",
 "iqm2:okaloosa cal": "https://okaloosacountyfl.iqm2.com/Citizens/Calendar.aspx",
 "iqm2:miami rss": "https://miamifl.iqm2.com/Services/RSS.aspx?Feed=Calendar",
 "iqm2:miami cal": "https://miamifl.iqm2.com/Citizens/Calendar.aspx",
 "iqm2:fwb rss": "https://fortwaltonbeachcityfl.iqm2.com/Services/RSS.aspx?Feed=Calendar",
 # eScribe / PrimeGov
 "escribe:alachua": "https://pub-alachuacounty.escribemeetings.com/MeetingsCalendarView.aspx",
 "escribe:cutlerbay": "https://pub-cutlerbay-fl.escribemeetings.com/MeetingsCalendarView.aspx",
 "primegov:bay upcoming": "https://baycountyfl.primegov.com/api/v2/PublicPortal/ListUpcomingMeetings",
 "primegov:bay archived": f"https://baycountyfl.primegov.com/api/v2/PublicPortal/ListArchivedMeetings?year={Y}",
 # Granicus publisher pages
 "granicus:monroe": "https://monroecountyfl.granicus.com/ViewPublisher.php?view_id=1",
 "granicus:boca": "https://bocaraton.granicus.com/ViewPublisher.php?view_id=2",
 "granicus:plantation": "https://plantation.granicus.com/ViewPublisher.php?view_id=2",
 "granicus:tamarac": "https://tamarac.granicus.com/ViewPublisher.php?view_id=2",
 "granicus:lighthousepoint": "https://city-lighthousepoint.granicus.com/ViewPublisher.php?view_id=1",
 "granicus:safetyharbor": "https://safetyharbor.granicus.com/ViewPublisher.php?view_id=1",
 # CivicPlus AgendaCenter (listing + RSS)
 "agendacenter:aventura": "https://www.cityofaventura.com/AgendaCenter",
 "agendacenter:aventura rss": "https://www.cityofaventura.com/RSSFeed.aspx?ModID=65&CID=All-0",
 "agendacenter:northmiami": "https://www.northmiamifl.gov/AgendaCenter",
 "agendacenter:sweetwater": "https://cityofsweetwater.fl.gov/AgendaCenter",
 "agendacenter:davie": "https://www.davie-fl.gov/AgendaCenter",
 "agendacenter:keywest": "https://www.cityofkeywest-fl.gov/AgendaCenter",
 "agendacenter:lakemary": "https://www.lakemaryfl.com/AgendaCenter",
 "agendacenter:groveland": "https://www.groveland-fl.gov/AgendaCenter",
 "agendacenter:bartow": "https://www.cityofbartow.net/AgendaCenter",
 "agendacenter:pinellaspark": "https://www.pinellaspark.gov/AgendaCenter",
 "agendacenter:levy": "https://www.levycounty.org/AgendaCenter",
 "agendacenter:seminole": "https://www.myseminole.com/AgendaCenter",
 # Others
 "novus:lauderdalelakes": "https://lauderdalelakes.novusagenda.com/agendapublic/",
 "novus:davie": "https://davie.novusagenda.com/agendapublic/",
 "municode:lakepark": "https://lakepark-fl.municodemeetings.com/",
 "civicclerk:stuart": "https://stuartfl.api.civicclerk.com/v1/Events?$top=3&$orderby=startDateTime%20desc",
 "civicclerk:winterpark": "https://winterparkfl.api.civicclerk.com/v1/Events?$top=3&$orderby=startDateTime%20desc",
 "civicclerk:cocoabeach": "https://cocoabeachfl.api.civicclerk.com/v1/Events?$top=3&$orderby=startDateTime%20desc",
 "miamidade:list": "https://www.miamidade.gov/govaction/agendas.asp?Action=Agendas&Oper=DisplayList",
 "manatee:onbase": "https://agendaonline.mymanatee.org/OnBaseAgendaOnline/",
 "leon:list": "https://www2.leoncountyfl.gov/coadmin/agenda/list.asp",
 "palmcoast:list": "https://www.palmcoast.gov/agendas/meetings/city-council/2026",
 "weston:list": "https://www.westonfl.org/government/agendas-minutes",
 "satellitebeach:cc": "https://www.satellitebeach.gov/government/city-council/",
 "newportrichey:docs": "https://www.cityofnewportrichey.org/",
 "diligent:pasco": "https://pasco-k12-fl.community.diligentoneplatform.com/portal/",
 "diligent:palmbeach": "https://palmbeachschools-org.community.diligentoneplatform.com/Portal/",
 "stlucie-sd:agendas": "https://www.stlucie.k12.fl.us/our-district/board-agendas-and-minutes/",
}
out = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": {}}
for name, url in T.items():
    r = {"url": url}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as resp:
            body = resp.read(400000).decode("utf-8", "replace"); r.update(status=resp.status, final_url=resp.geturl())
    except urllib.error.HTTPError as e:
        body = e.read(20000).decode("utf-8", "replace") if e.fp else ""; r["status"] = e.code
    except Exception as e:
        body = ""; r["status"] = None; r["error"] = str(e)[:200]
    r["bytes"] = len(body); r["challenge"] = bool(CH.search(body[:20000]))
    r["pdf_links"] = len(re.findall(r'(?i)href="[^"]+\.pdf|ViewFile/Agenda|FileOpen\.aspx|View\.ashx|AgendaViewer|filestream\.ashx|DownloadFile|GetMeetingFileStream', body))
    r["dates_2026"] = len(re.findall(r"(?:1[0-2]|0?[1-9])/\d{1,2}/2026|2026-\d\d-\d\d|(?:Nov|Dec|Oct)[a-z]*\.? \d{1,2}, 2026", body))
    r["snippet"] = " ".join(re.sub(r"<[^>]+>", " ", body).split())[:300]
    out["results"][name] = r
    time.sleep(2)
open("data/probe_dead.json", "w").write(json.dumps(out, indent=1))
for k, v in out["results"].items():
    print(f"{k:28} {v.get('status')} {v['bytes']:7} chal={int(v['challenge'])} links={v['pdf_links']} d26={v['dates_2026']}")
