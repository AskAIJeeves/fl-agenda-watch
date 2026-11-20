"""Pull upcoming and recent agenda items from Legistar Web API clients and
flag large-dollar spending items. Writes data/agenda_items.json and
data/agenda_status.json. Standard library only."""
import json, re, sys, time, urllib.request, urllib.parse
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import rules
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://webapi.legistar.com/v1/{client}/{path}"
UA = {"User-Agent": "Mozilla/5.0 (compatible; floridaspending.com agenda reader; +https://floridaspending.com)", "Accept": "application/json"}

KEYWORDS = re.compile(r"\b(bonds?|debt|loan|refund(ing)?|design[- ]build|construction|change order|"
                      r"guaranteed maximum price|gmp|contract|agreement|purchase|lease|"
                      r"golf|marina|stadium|arena|city hall|government center|library|"
                      r"consultant|sole source|no[- ]bid|piggyback|settlement)\b", re.I)
MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(million|billion|m\b|mm\b)?", re.I)

def get(client, path, params=None):
    url = API.format(client=client, path=path)
    if params:
        url += "?" + urllib.parse.urlencode(params, safe="$'(),:")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404, 500):
                raise
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("request failed after retries")

def amounts(text):
    out = []
    for num, unit in MONEY.findall(text or ""):
        v = float(num.replace(",", ""))
        u = (unit or "").lower()
        if u in ("million", "m", "mm"): v *= 1e6
        elif u == "billion": v *= 1e9
        out.append(v)
    return out

def odate(d):
    return "datetime'%s'" % d.strftime("%Y-%m-%d")

def scan(gov, cfg, now):
    start, end = now - timedelta(days=cfg["lookback_days"]), now + timedelta(days=cfg["lookahead_days"])
    flt = "EventDate ge %s and EventDate lt %s" % (odate(start), odate(end))
    last_err = None
    for client in gov["candidates"]:
        try:
            events = get(client, "events", {"$filter": flt, "$orderby": "EventDate"})
        except Exception as e:
            last_err = f"{client}: {e}"
            continue
        items = []
        for ev in events:
            try:
                eis = get(client, f"events/{ev['EventId']}/eventitems", {"AgendaNote": 1, "MinutesNote": 0, "Attachments": 0})
            except Exception:
                continue
            for it in eis:
                text = " ".join(filter(None, [it.get("EventItemTitle"), it.get("EventItemMatterName"), it.get("EventItemAgendaNote")]))
                if not text.strip():
                    continue
                tags = rules.classify(text)
                if tags:
                    items.append({
                        "entity_id": gov["entity_id"], "government": gov["name"], "client": client,
                        "body": ev.get("EventBodyName"), "meeting_date": (ev.get("EventDate") or "")[:10],
                        "agenda_number": it.get("EventItemAgendaNumber"), "file_number": it.get("EventItemMatterFile"),
                        "title": (it.get("EventItemTitle") or "")[:1500], **tags,
                        "keywords": sorted({m.group(0).lower() for m in KEYWORDS.finditer(text)}),
                        "meeting_url": ev.get("EventInSiteURL"), "agenda_pdf": ev.get("EventAgendaFile"),
                        "item_url": (f"https://{client}.legistar.com/gateway.aspx?M=L&ID={it['EventItemMatterId']}" if it.get("EventItemMatterId") else ev.get("EventInSiteURL")),
                    })
        return {"status": "ok", "client": client, "events": len(events), "flagged": len(items)}, items
    return {"status": "failed", "error": last_err}, []

def main():
    cfg = json.loads((ROOT / "config/governments.json").read_text())
    now = datetime.now(timezone.utc)
    status, all_items = {}, []
    for gov in cfg["governments"]:
        st, items = scan(gov, cfg, now)
        status[gov["entity_id"]] = {"name": gov["name"], **st}
        all_items += items
        print(gov["name"], st, file=sys.stderr)
    # one row per matter: merge repeat appearances across committees and meetings
    merged = {}
    for it in all_items:
        key = (it["client"], it["file_number"] or it["title"][:200])
        m = merged.get(key)
        if not m:
            it["appearances"] = [{"body": it["body"], "meeting_date": it["meeting_date"]}]
            merged[key] = it
        else:
            m["appearances"].append({"body": it["body"], "meeting_date": it["meeting_date"]})
    all_items = list(merged.values())
    all_items.sort(key=lambda x: (-(x.get("signal_score") or 0), x["meeting_date"]))
    (ROOT / "data").mkdir(exist_ok=True)
    meta = {"generated_utc": now.isoformat(timespec="seconds"), "count": len(all_items)}
    (ROOT / "data/agenda_items.json").write_text(json.dumps({**meta, "items": all_items}, indent=1))
    (ROOT / "data/agenda_status.json").write_text(json.dumps({**meta, "governments": status}, indent=1))

if __name__ == "__main__":
    main()
