"""One-time backfill of past Legistar meetings into the permanent archive.

Works through (government, month) chunks, newest first: all of 2026, then
2025 and 2024. For 2024-2025 only big-ticket items are kept (amount >= $5M,
or a facilities/debt item >= $1M), since those are the multi-year
commitments still being spent. Progress is saved in
data/backfill_state.json so each run picks up where the last one stopped.
Stops after TIME_BUDGET seconds.
"""
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_items
import rules
from fetch_agendas import KEYWORDS, get

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data/backfill_state.json"
TIME_BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 40 * 60
DEBT = re.compile(r"\b(bonds?|debt|loan|refunding|note[s]?\s+payable|line of credit|design[- ]build|"
                  r"guaranteed maximum price|gmp|construction)\b", re.I)


def months():
    out = []
    for y in (2026, 2025, 2024):
        last = date.today().month if y == date.today().year else 12
        out += [(y, m) for m in range(last, 0, -1)]
    return out


def big_ticket(tags, text):
    amt = tags.get("max_amount") or 0
    return amt >= 5e6 or (amt >= 1e6 and ("facilities" in tags["signals"] or DEBT.search(text)))


def chunk(gov, client, y, m):
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    flt = "EventDate ge datetime'%s' and EventDate lt datetime'%s'" % (start, end)
    events = get(client, "events", {"$filter": flt, "$orderby": "EventDate"})
    items = []
    for ev in events:
        try:
            eis = get(client, f"events/{ev['EventId']}/eventitems",
                      {"AgendaNote": 1, "MinutesNote": 0, "Attachments": 0})
        except Exception:
            continue
        for it in eis:
            text = " ".join(filter(None, [it.get("EventItemTitle"), it.get("EventItemMatterName"),
                                          it.get("EventItemAgendaNote")]))
            tags = rules.classify(text) if text.strip() else None
            if not tags or (y < 2026 and not big_ticket(tags, text)):
                continue
            items.append({
                "entity_id": gov["entity_id"], "government": gov["name"], "client": client,
                "body": ev.get("EventBodyName"), "meeting_date": (ev.get("EventDate") or "")[:10],
                "agenda_number": it.get("EventItemAgendaNumber"), "file_number": it.get("EventItemMatterFile"),
                "title": (it.get("EventItemTitle") or "")[:1500], **tags,
                "keywords": sorted({k.group(0).lower() for k in KEYWORDS.finditer(text)}),
                "meeting_url": ev.get("EventInSiteURL"), "agenda_pdf": ev.get("EventAgendaFile"),
                "item_url": (f"https://{client}.legistar.com/gateway.aspx?M=L&ID={it['EventItemMatterId']}"
                             if it.get("EventItemMatterId") else ev.get("EventInSiteURL")),
                # passage/vote outcome as recorded by the clerk, when available
                "action": it.get("EventItemActionName"), "passed": it.get("EventItemPassedFlagName"),
                "tally": it.get("EventItemTally"),
            })
    return len(events), items


def main():
    t0 = time.time()
    govs = json.loads((ROOT / "config/governments.json").read_text())["governments"]
    status = json.loads((ROOT / "data/agenda_status.json").read_text())["governments"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {"done": {}, "errors": {}}
    work = [(g, y, m) for (y, m) in months() for g in govs
            if status.get(g["entity_id"], {}).get("client")
            and f"{g['entity_id']}|{y}-{m:02d}" not in state["done"]]
    print(f"{len(work)} chunks remaining")
    batch, n = [], 0
    for g, y, m in work:
        if time.time() - t0 > TIME_BUDGET:
            break
        k = f"{g['entity_id']}|{y}-{m:02d}"
        try:
            ev, items = chunk(g, status[g["entity_id"]]["client"], y, m)
            state["done"][k] = {"events": ev, "kept": len(items)}
            state["errors"].pop(k, None)
            batch += items
        except Exception as e:
            state["errors"][k] = str(e)[:200]
        n += 1
        if len(batch) >= 300:          # flush periodically so a timeout loses little
            archive_items.merge(batch, "legistar_backfill")
            batch = []
            STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    archive_items.merge(batch, "legistar_backfill")
    state["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["remaining"] = len(work) - n
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
    print(f"processed {n} chunks, {state['remaining']} remaining, {len(state['errors'])} errors, "
          f"archive total {archive_items.total()}")


if __name__ == "__main__":
    main()
