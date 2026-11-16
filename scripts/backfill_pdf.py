"""One-time backfill of 2026 agendas from the PDF platforms that list past
meetings by date: CivicClerk, CivicWeb and PrimeGov. Newest meetings first.
Each document is scanned with the same rules as the nightly reader and the
results go straight into the permanent archive. Progress is kept in
data/backfill_pdf_state.json; stops after TIME_BUDGET seconds.
"""
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_items
from fetch_pdf_agendas import eagenda_docs, fetch, scan_doc

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data/backfill_pdf_state.json"
TIME_BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 40 * 60
START = "2026-01-01"


def list_docs(cfg, today, errors):
    """Return [(mdate, platform, entity_id, name, body, doc_url, meeting_url)]."""
    skip = re.compile(cfg.get("meeting_skip") or "$^")
    out = []
    for cc in cfg.get("civicclerk", []):
        base = f"https://{cc['tenant']}.api.civicclerk.com/v1"
        url = None
        q = urllib.parse.urlencode({"$filter": f"startDateTime ge {START}T00:00:00Z and startDateTime lt {today}T00:00:00Z",
                                    "$orderby": "startDateTime desc", "$top": "100"}, safe="$ :")
        url = f"{base}/Events?{q}"
        pages = 0
        while url and pages < 10:
            try:
                js = json.loads(fetch(url))
            except Exception as e:
                errors[cc["entity_id"]] = f"civicclerk list: {e}"[:200]
                break
            for ev in js.get("value", []):
                name = ev.get("eventName") or ev.get("categoryName") or ""
                if skip.search(name):
                    continue
                files = [f for f in ev.get("publishedFiles") or []
                         if f.get("fileId") and re.search(r"(?i)agenda|packet", (f.get("type") or "") + " " + (f.get("name") or ""))]
                for f in files[:1]:
                    out.append(((ev.get("startDateTime") or "")[:10], "civicclerk", cc["entity_id"], cc["name"], name,
                                f"{base}/Meetings/GetMeetingFileStream(fileId={f['fileId']},plainText=false)",
                                f"https://{cc['tenant']}.portal.civicclerk.com/"))
            url = js.get("@odata.nextLink")
            pages += 1
    for g in cfg.get("civicweb", []):
        try:
            ms = json.loads(fetch(f"https://{g['host']}/Services/MeetingsService.svc/meetings?from={START}&to={today}"))
        except Exception as e:
            errors[g["entity_id"]] = f"civicweb list: {e}"[:200]
            continue
        for m in ms:
            if not skip.search(m.get("Name", "")):
                out.append((m.get("MeetingDate", "")[:10], "civicweb", g["entity_id"], g["name"], m.get("Name"),
                            None, f"https://{g['host']}/Portal/MeetingInformation.aspx?Id={m['Id']}"))
    for g in cfg.get("primegov", []):
        try:
            ms = json.loads(fetch(f"https://{g['host']}/api/v2/PublicPortal/ListArchivedMeetings?year=2026"))
        except Exception as e:
            errors[g["entity_id"]] = f"primegov list: {e}"[:200]
            continue
        for m in ms:
            d = (m.get("dateTime") or "")[:10]
            if not (START <= d < today) or skip.search(m.get("title") or ""):
                continue
            docs = [x for x in m.get("documentList", []) if x.get("compileOutputType") == 1
                    and re.search(r"(?i)agenda", x.get("templateName", ""))]
            for x in docs[:1]:
                out.append((d, "primegov", g["entity_id"], g["name"], m.get("title"),
                            f"https://{g['host']}/Public/CompiledDocument?meetingTemplateId={x['templateId']}&compileOutputType=1",
                            f"https://{g['host']}/Portal/Meeting?meetingTemplateId={x['templateId']}"))
    for g in cfg.get("eagenda", []):
        try:
            for dt, u, body in eagenda_docs(g, START, today, max_pages=12):
                out.append((dt, "eagenda", g["entity_id"], g["name"], body, u, g["base"] + "/home"))
        except Exception as e:
            errors[g["entity_id"]] = f"eagenda list: {e}"[:200]
    return sorted(out, key=lambda r: r[0], reverse=True)


def main():
    t0 = time.time()
    cfg = json.loads((ROOT / "config/pdf_sources.json").read_text())
    cfg = {**cfg, "max_pages_per_pdf": min(cfg.get("max_pages_per_pdf", 400), 200)}
    state = json.loads(STATE.read_text()) if STATE.exists() else {"seen": {}, "list_errors": {}}
    now = datetime.now(timezone.utc)
    errors = {}
    docs = list_docs(cfg, now.date().isoformat(), errors)
    state["list_errors"] = errors
    todo = [r for r in docs if (r[5] or r[6]) not in state["seen"]]
    print(f"{len(docs)} meetings listed, {len(todo)} to scan")
    batch, n = [], 0
    for mdate, plat, eid, name, body, u, mu in todo:
        if time.time() - t0 > TIME_BUDGET:
            break
        key = u or mu
        if plat == "civicweb":       # find the agenda document on the meeting page
            try:
                page = fetch(mu)
                found = sorted(set(x.replace("&amp;", "&") for x in re.findall(r'(/document/\d+/[^"\']+)', page)),
                               key=lambda x: (0 if re.search(r"(?i)agenda|package|packet", x) else 1))
                u = f"https://{urllib.parse.urlparse(mu).netloc}{found[0]}" if found else None
            except Exception:
                u = None
            if not u:
                state["seen"][key] = {"status": "no_doc"}
                continue
        store, d = {"items": []}, {"scanned": [], "errors": []}
        scan_doc(store, {}, d, cfg, now, eid, name, plat, body, mdate, u, mu, final=True)
        batch += store["items"]
        state["seen"][key] = {"status": "error" if d["errors"] else "ok", "hits": len(store["items"]), "date": mdate,
                              **({"error": d["errors"][0][:200]} if d["errors"] else {})}
        n += 1
        if len(batch) >= 300:
            archive_items.merge(batch, "pdf_backfill")
            batch = []
            STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    archive_items.merge(batch, "pdf_backfill")
    state["remaining"] = len(todo) - n
    state["updated_utc"] = now.isoformat(timespec="seconds")
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    print(f"scanned {n}, remaining {state['remaining']}, list errors {len(errors)}, archive total {archive_items.total()}")


if __name__ == "__main__":
    main()
