"""One-off: scan Hillsborough County BOCC agendas for 2026 from eAgenda into the archive."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import archive_items
from fetch_pdf_agendas import eagenda_docs, scan_doc
cfg = json.loads((ROOT / "config/pdf_sources.json").read_text())
cfg = {**cfg, "max_pages_per_pdf": 400}
g = cfg["eagenda"][0]
now = datetime.now(timezone.utc)
docs = eagenda_docs(g, "2026-01-01", now.date().isoformat(), max_pages=12)
stp = ROOT / "data/backfill_pdf_state.json"
st = json.loads(stp.read_text())
store, d = {"items": []}, {"scanned": [], "errors": []}
for dt, u, body in docs:
    if u in st["seen"]: continue
    before = len(store["items"])
    scan_doc(store, {}, d, cfg, now, g["entity_id"], g["name"], "eagenda", body, dt, u, g["base"] + "/home", final=True)
    st["seen"][u] = {"status": "ok", "hits": len(store["items"]) - before, "date": dt}
print(archive_items.merge(store["items"], "pdf_backfill"), len(store["items"]), d["errors"][:3])
print(json.dumps(d["scanned"], indent=0)[:2000])
stp.write_text(json.dumps(st, indent=1, sort_keys=True))
