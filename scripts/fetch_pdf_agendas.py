"""Watch agenda listing pages for governments without a usable data feed,
download new agenda PDFs, and flag passages with large dollar amounts.
Adds items to data/pdf_items.json (same fields as agenda_items) and keeps
data/pdf_seen.json so each PDF is scanned once. Needs: pypdf."""
import io, json, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_agendas import amounts, KEYWORDS  # shared filters

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

def fetch(url, binary=False):
    url = urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        return data if binary else data.decode(r.headers.get_content_charset() or "utf-8", "replace")

def links(url):
    p = Links(url); p.feed(fetch(url)); return p.out

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
            if top and top >= min_amount:
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
            d["listing"].append({"url": lu, "links": len(ls), "sample": [[u, t] for u, t in ls if re.search(r"(?i)agenda|meeting|council|commission|pdf|onbase|legistar|iqm2|packet", u + " " + t)][:120]})
            pages = [lu]
            if follow_re:
                pages += list(dict.fromkeys(u for u, _ in ls if follow_re.search(u) and u != lu))[:6]
            for pu in pages:
                try:
                    pl = ls if pu == lu else links(pu)
                except Exception as e:
                    d["errors"].append(f"page {pu}: {e}"); continue
                for u, t in pl:
                    if pdf_re.search(u): cands.append((u, t, pu))
        cands = list(dict((u, (u, t, p)) for u, t, p in cands).values())
        d["pdfs_found"] = len(cands)
        d["pdf_sample"] = [c[0] for c in cands[:15]]
        new = [c for c in cands if c[0] not in seen][: cfg["max_new_pdfs_per_run"]]
        for u, title, page in new:
            try:
                data = fetch(u, binary=True)
                if not data[:5].startswith(b"%PDF"):
                    seen[u] = {"status": "not_pdf", "date": now.date().isoformat()}; continue
                pages = pdf_text(data, cfg["max_pages_per_pdf"])
                hits = passages(pages, min_amount)
                for pno, top, ch in hits:
                    store["items"].append({
                        "entity_id": src["entity_id"], "government": src["name"], "client": "pdf",
                        "body": title or None, "meeting_date": None, "agenda_number": f"p.{pno}",
                        "file_number": None, "title": ch, "max_amount": top,
                        "keywords": sorted({m.group(0).lower() for m in KEYWORDS.finditer(ch)}),
                        "meeting_url": page, "agenda_pdf": u, "found_utc": now.isoformat(timespec="seconds")})
                seen[u] = {"status": "ok", "pages": len(pages), "hits": len(hits), "date": now.date().isoformat()}
                d["scanned"].append({"pdf": u, "pages": len(pages), "hits": len(hits)})
            except Exception as e:
                d["errors"].append(f"pdf {u}: {e}")
            time.sleep(1)
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
