"""Watch agenda listing pages for governments without a usable data feed,
download new agenda PDFs, and flag passages with large dollar amounts.
Adds items to data/pdf_items.json (same fields as agenda_items) and keeps
data/pdf_seen.json so each PDF is scanned once. Needs: pypdf."""
import io, json, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_agendas import amounts, KEYWORDS  # shared filters

ACTION = re.compile(r"(?i)\b(approv\w*|award\w*|authoriz\w*|not[- ]to[- ]exceed|contract|agreement|amendment|change order|purchase|resolution|ordinance|appropriat\w*|bond|loan)\b")
UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public records research)"}

class Links(HTMLParser):
    def __init__(self, base):
        super().__init__(); self.base, self.out, self._a, self._t = base, [], None, []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href: self._a, self._t = urllib.parse.urljoin(self.base, href.strip()), []
    def handle_data(self, d):
        if self._a: self._t.append(d)
    def handle_endtag(self, tag):
        if tag == "a" and self._a:
            self.out.append((self._a, " ".join(" ".join(self._t).split()))); self._a = None

class FixS3(urllib.request.HTTPRedirectHandler):
    """Granicus redirects to a bucket hostname with an underscore, which fails TLS; use path-style S3."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = re.sub(r"^https?://([a-z0-9_]+_[a-z0-9_]*)\.s3\.amazonaws\.com/", r"https://s3.amazonaws.com/\1/", newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)
OPENER = urllib.request.build_opener(FixS3)

def fetch(url, binary=False):
    url = urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")
    req = urllib.request.Request(url, headers=UA)
    with OPENER.open(req, timeout=60) as r:
        data = r.read()
        return data if binary else data.decode(r.headers.get_content_charset() or "utf-8", "replace")

def links(url):
    body = fetch(url)
    if "<rss" in body[:500] or "<channel>" in body[:2000]:  # RSS feed: use item links
        out = []
        for item in re.findall(r"(?is)<item>(.*?)</item>", body):
            lk = re.search(r"(?is)<link>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</link>", item)
            tt = re.search(r"(?is)<title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>", item)
            if lk: out.append((urllib.parse.urljoin(url, lk.group(1).strip().replace("&amp;", "&")), (tt.group(1).strip() if tt else "")))
        return out
    p = Links(url); p.feed(body); return p.out

def pdf_text(data, max_pages):
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, pg in enumerate(reader.pages[:max_pages]):
        try: pages.append((i + 1, pg.extract_text() or ""))
        except Exception: pages.append((i + 1, ""))
    return pages

def passages(pages, min_amount):
    """Split each page into paragraph-ish chunks and keep ones with big dollars."""
    out = []
    for pno, txt in pages:
        chunks = re.split(r"\n\s*\n|(?=\n\s*(?:\d{1,2}|[A-Z])[\.\)]\s)", txt)
        for ch in chunks:
            ch = " ".join(ch.split())
            if len(ch) < 40: continue
            a = amounts(ch)
            top = max(a) if a else None
            if top and top >= min_amount and ACTION.search(ch):
                out.append((pno, top, ch[:1200]))
    # drop near-duplicate passages (agenda + packet repeat the same item)
    seen, uniq = set(), []
    for p in sorted(out, key=lambda x: -x[1]):
        k = (round(p[1]), p[2][:120])
        if k not in seen: seen.add(k); uniq.append(p)
    return uniq

def main():
    cfg = json.loads((ROOT / "config/pdf_sources.json").read_text())
    gov_cfg = json.loads((ROOT / "config/governments.json").read_text())
    min_amount = gov_cfg["min_amount"]
    seen_p, items_p = ROOT / "data/pdf_seen.json", ROOT / "data/pdf_items.json"
    seen = json.loads(seen_p.read_text()) if seen_p.exists() else {}
    store = json.loads(items_p.read_text()) if items_p.exists() else {"items": []}
    debug, now = {}, datetime.now(timezone.utc)
    for src in cfg["sources"]:
        d = debug[src["entity_id"]] = {"name": src["name"], "listing": [], "pdfs_found": 0, "scanned": [], "errors": []}
        pdf_re, follow_re = re.compile(src["pdf"]), re.compile(src["follow"]) if src["follow"] else None
        cands = []
        for lu in src["listing_urls"]:
            try:
                ls = links(lu)
            except Exception as e:
                d["errors"].append(f"listing {lu}: {e}"); continue
            try: head = fetch(lu)[:300]
            except Exception as e: head = str(e)
            d["listing"].append({"url": lu, "links": len(ls), "head": head, "sample": [[u, t] for u, t in ls if re.search(r"(?i)agenda|meeting|council|commission|pdf|onbase|legistar|iqm2|packet", u + " " + t)][:120]})
            pages = [lu]
            if follow_re:
                pages += list(dict.fromkeys(u for u, _ in ls if follow_re.search(u) and u != lu))[:10]
            for pu in pages:
                try:
                    pl = ls if pu == lu else links(pu)
                except Exception as e:
                    d["errors"].append(f"page {pu}: {e}"); continue
                if pu != lu:
                    d.setdefault("followed", []).append({"url": pu, "links": len(pl), "sample": [[u, t] for u, t in pl if re.search(r"(?i)agenda|meeting|pdf|document|file|packet|legistar", u + " " + t)][:60]})
                for u, t in pl:
                    if pdf_re.search(u): cands.append((u, t, pu))
        cands = list(dict((u, (u, t, p)) for u, t, p in cands).values())
        d["pdfs_found"] = len(cands)
        d["pdf_sample"] = [c[0] for c in cands[:15]]
        def udate(u):
            uu = urllib.parse.unquote(u)
            m = re.search(r"(20\d\d)[-_ ]?(\d\d)[-_ ]?(\d\d)", uu)
            try:
                if m and 1 <= int(m[2]) <= 12: return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
                m = re.search(r"_(\d\d)(\d\d)(20\d\d)-", uu)  # CivicPlus _MMDDYYYY-
                if m: return datetime(int(m[3]), int(m[1]), int(m[2]), tzinfo=timezone.utc)
            except ValueError: pass
            return None
        recent = [c for c in cands if not udate(c[0]) or (now - udate(c[0])).days <= 45]
        new = [c for c in recent if c[0] not in seen][: cfg["max_new_pdfs_per_run"]]
        for u, title, page in new:
            try:
                data = fetch(u, binary=True)
                if data[:5].startswith(b"%PDF"):
                    pages = pdf_text(data, cfg["max_pages_per_pdf"])
                elif b"<html" in data[:2000].lower():
                    html = data.decode("utf-8", "replace")
                    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
                    txt = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n\n", html)
                    txt = re.sub(r"<[^>]+>", " ", txt)
                    import html as _h; pages = [(1, _h.unescape(txt))]
                else:
                    seen[u] = {"status": "not_pdf", "date": now.date().isoformat()}; continue
                hits = passages(pages, min_amount)[:30]
                for pno, top, ch in hits:
                    store["items"].append({
                        "entity_id": src["entity_id"], "government": src["name"], "client": "pdf",
                        "body": title or None, "meeting_date": udate(u).date().isoformat() if udate(u) else None, "agenda_number": f"p.{pno}",
                        "file_number": None, "title": ch, "max_amount": top,
                        "keywords": sorted({m.group(0).lower() for m in KEYWORDS.finditer(ch)}),
                        "meeting_url": page, "agenda_pdf": u, "found_utc": now.isoformat(timespec="seconds")})
                seen[u] = {"status": "ok", "pages": len(pages), "hits": len(hits), "date": now.date().isoformat()}
                d["scanned"].append({"pdf": u, "pages": len(pages), "hits": len(hits)})
            except Exception as e:
                d["errors"].append(f"pdf {u}: {e}")
            time.sleep(1)
    # CivicClerk tenants: list recent/upcoming events with published agenda files via the public API
    for cc in cfg.get("civicclerk", []):
        d = debug[cc["entity_id"] + ":civicclerk"] = {"name": cc["name"], "platform": "civicclerk", "events": 0, "files": [], "scanned": [], "errors": []}
        base = f"https://{cc['tenant']}.api.civicclerk.com/v1"
        start = (now - timedelta(days=10)).strftime("%Y-%m-%dT00:00:00Z")
        try:
            q = urllib.parse.urlencode({"$filter": f"startDateTime ge {start}", "$orderby": "startDateTime asc", "$top": "40"}, safe="$ :")
            evs = json.loads(fetch(f"{base}/Events?{q}")).get("value", [])
        except Exception as e:
            d["errors"].append(f"events: {e}"); continue
        d["events"] = len(evs)
        todo = []
        for ev in evs:
            for f in ev.get("publishedFiles") or []:
                if re.search(r"(?i)agenda|packet", (f.get("type") or "") + " " + (f.get("name") or "")) and f.get("fileId"):
                    u = f"{base}/Meetings/GetMeetingFileStream(fileId={f['fileId']},plainText=false)"
                    todo.append((u, ev.get("eventName") or ev.get("categoryName"), (ev.get("startDateTime") or "")[:10]))
        d["files"] = [t[0] for t in todo[:10]]
        for u, body, mdate in [t for t in todo if t[0] not in seen][: cfg["max_new_pdfs_per_run"]]:
            try:
                data = fetch(u, binary=True)
                if not data[:5].startswith(b"%PDF"):
                    seen[u] = {"status": "not_pdf", "date": now.date().isoformat()}; d["errors"].append(f"not pdf: {u} {data[:80]!r}"); continue
                pages = pdf_text(data, cfg["max_pages_per_pdf"]); hits = passages(pages, min_amount)[:30]
                for pno, top, ch in hits:
                    store["items"].append({"entity_id": cc["entity_id"], "government": cc["name"], "client": "civicclerk",
                        "body": body, "meeting_date": mdate, "agenda_number": f"p.{pno}", "file_number": None, "title": ch,
                        "max_amount": top, "keywords": sorted({m.group(0).lower() for m in KEYWORDS.finditer(ch)}),
                        "meeting_url": f"https://{cc['tenant']}.portal.civicclerk.com/", "agenda_pdf": u, "found_utc": now.isoformat(timespec="seconds")})
                chars = sum(len(t) for _, t in pages)
                seen[u] = {"status": "ok", "pages": len(pages), "hits": len(hits), "chars": chars, "date": now.date().isoformat()}
                d["scanned"].append({"pdf": u, "pages": len(pages), "hits": len(hits), "chars": chars, "meeting_date": mdate})
            except Exception as e:
                d["errors"].append(f"pdf {u}: {e}")
            time.sleep(1)

    # OnBase Agenda Online (Tampa, Osceola): meeting list is JSON embedded in the search page
    for ob in cfg.get("onbase", []):
        d = debug[ob["entity_id"] + ":onbase"] = {"name": ob["name"], "platform": "onbase", "meetings": 0, "with_agenda": 0, "scanned": [], "errors": []}
        try:
            html = fetch(ob["base"] + "/Meetings/Search?dropid=4&mtids=")
            i = html.find('"Meetings":['); st = html.rfind("SearchResults(", 0, i) + len("SearchResults(")
            depth = 0
            for j in range(st, len(html)):
                if html[j] == "{": depth += 1
                elif html[j] == "}":
                    depth -= 1
                    if depth == 0: break
            meetings = json.loads(html[st:j + 1])["Meetings"]
        except Exception as e:
            d["errors"].append(f"meeting list: {e}"); continue
        d["meetings"] = len(meetings)
        skip = re.compile(ob.get("skip") or "$^")
        todo = []
        for m in meetings:
            try: when = datetime.fromisoformat(m["Time"])
            except Exception: continue
            age = (now - when).days
            if not m.get("IsAgendaAvailable") or skip.search(m.get("Name") or "") or age > 14 or age < -30: continue
            u = f"{ob['base']}/Documents/DownloadFile/{urllib.parse.quote(m['AgendaUniqueName'])}.pdf?documentType=1&meetingId={m['ID']}"
            todo.append((u, m["Name"], when.date().isoformat(), m["ID"]))
        d["with_agenda"] = len(todo)
        for u, body, mdate, mid in [t for t in todo if t[0] not in seen][: cfg["max_new_pdfs_per_run"] + 2]:
            try:
                data = fetch(u, binary=True)
                if not data[:5].startswith(b"%PDF"):
                    d["errors"].append(f"not pdf: {u[-80:]} {data[:60]!r}"); continue
                pages = pdf_text(data, cfg["max_pages_per_pdf"]); hits = passages(pages, min_amount)[:40]
                for pno, top, ch in hits:
                    store["items"].append({"entity_id": ob["entity_id"], "government": ob["name"], "client": "onbase",
                        "body": body, "meeting_date": mdate, "agenda_number": f"p.{pno}", "file_number": None, "title": ch,
                        "max_amount": top, "keywords": sorted({mm.group(0).lower() for mm in KEYWORDS.finditer(ch)}),
                        "meeting_url": f"{ob['base']}/Meetings/ViewMeeting?id={mid}&doctype=1", "agenda_pdf": u,
                        "found_utc": now.isoformat(timespec="seconds")})
                # agendas get revised before the meeting: only mark done once the meeting has passed
                if mdate < now.date().isoformat(): seen[u] = {"status": "ok", "pages": len(pages), "hits": len(hits), "date": now.date().isoformat()}
                d["scanned"].append({"pdf": u[-90:], "meeting": body, "pages": len(pages), "hits": len(hits)})
            except Exception as e:
                d["errors"].append(f"pdf {u[-80:]}: {e}")
            time.sleep(1)

    # date-patterned PDFs (Palm Beach, Manatee): try each date from 7 days back to 21 days ahead
    for dt in cfg.get("date_template", []):
        d = debug[dt["entity_id"] + ":date"] = {"name": dt["name"], "platform": "date_template", "found": [], "scanned": [], "errors": []}
        for off in range(-7, 22):
            day = now + timedelta(days=off)
            for tpl in dt["urls"]:
                u = tpl.format(Y=day.strftime("%Y"), m=day.strftime("%m"), d=day.strftime("%d"))
                if u in seen: continue
                try:
                    data = fetch(u, binary=True)
                    if not data[:5].startswith(b"%PDF"): continue
                except Exception:
                    continue
                d["found"].append(u)
                try:
                    pages = pdf_text(data, cfg["max_pages_per_pdf"]); hits = passages(pages, min_amount)[:30]
                    for pno, top, ch in hits:
                        store["items"].append({"entity_id": dt["entity_id"], "government": dt["name"], "client": "pdf",
                            "body": dt.get("body"), "meeting_date": day.date().isoformat(), "agenda_number": f"p.{pno}", "file_number": None,
                            "title": ch, "max_amount": top, "keywords": sorted({m.group(0).lower() for m in KEYWORDS.finditer(ch)}),
                            "meeting_url": None, "agenda_pdf": u, "found_utc": now.isoformat(timespec="seconds")})
                    # re-check future agendas (they get revised); mark past ones done
                    if off < 0: seen[u] = {"status": "ok", "pages": len(pages), "hits": len(hits), "date": now.date().isoformat()}
                    d["scanned"].append({"pdf": u, "pages": len(pages), "hits": len(hits)})
                except Exception as e:
                    d["errors"].append(f"pdf {u}: {e}")

    # numbered PDFs (Miami-Dade): probe keys after the last one found
    state_p = ROOT / "data/pdf_state.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
    for sq in cfg.get("sequential", []):
        d = debug[sq["entity_id"]] = {"name": sq["name"], "probed": [], "scanned": [], "errors": []}
        last = state.get(sq["entity_id"], sq["start_key"])
        misses, key, scanned = 0, last + 1, 0
        while misses < 12 and key <= last + sq["probe_ahead"] and scanned < cfg["max_new_pdfs_per_run"] + 4:
            u = sq["url"].format(key=key)
            try:
                data = fetch(u, binary=True)
                if not data[:5].startswith(b"%PDF"): raise ValueError("not pdf")
            except Exception:
                misses += 1; d["probed"].append([key, "miss"]); key += 1; continue
            misses = 0; d["probed"].append([key, "ok"]); state[sq["entity_id"]] = key; scanned += 1
            try:
                pages = pdf_text(data, cfg["max_pages_per_pdf"])
                first = " ".join((pages[0][1] if pages else "").split())[:400]
                m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (20\d\d)", first)
                mdate = datetime.strptime(" ".join(m.groups()), "%B %d %Y").date().isoformat() if m else None
                body = next((b for b in ["Board of County Commissioners", "Committee", "Policy Council"] if b in first), None)
                hits = passages(pages, min_amount)[:30]
                for pno, top, ch in hits:
                    store["items"].append({
                        "entity_id": sq["entity_id"], "government": sq["name"], "client": "pdf",
                        "body": body, "meeting_date": mdate, "agenda_number": f"p.{pno}", "file_number": None,
                        "title": ch, "max_amount": top,
                        "keywords": sorted({mm.group(0).lower() for mm in KEYWORDS.finditer(ch)}),
                        "meeting_url": None, "agenda_pdf": u, "found_utc": now.isoformat(timespec="seconds")})
                d["scanned"].append({"pdf": u, "pages": len(pages), "hits": len(hits), "meeting_date": mdate})
            except Exception as e:
                d["errors"].append(f"pdf {u}: {e}")
            key += 1; time.sleep(1)
    state_p.write_text(json.dumps(state, indent=1))
    # keep last 60 days of PDF findings
    cutoff = now.timestamp() - 60 * 86400
    store["items"] = [i for i in store["items"] if datetime.fromisoformat(i["found_utc"]).timestamp() >= cutoff]
    store.update(generated_utc=now.isoformat(timespec="seconds"), count=len(store["items"]))
    items_p.write_text(json.dumps(store, indent=1))
    seen_p.write_text(json.dumps(seen, indent=1))
    (ROOT / "data/pdf_debug.json").write_text(json.dumps({"generated_utc": now.isoformat(timespec="seconds"), "sources": debug}, indent=1))
    for k, v in debug.items(): print(v["name"], v["pdfs_found"], len(v["scanned"]), v["errors"][:2], file=sys.stderr)

if __name__ == "__main__":
    main()
