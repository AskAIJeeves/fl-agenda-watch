"""Test the eAgenda reader for Hillsborough County. Writes data/hcfl_probe.txt."""
import json, sys, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_pdf_agendas import eagenda_docs, fetch
cfg = json.loads((ROOT / "config/pdf_sources.json").read_text())
g = cfg["eagenda"][0]
out = []
try:
    html = fetch(g["base"] + "/results?F_MeetingType=Regular+BOCC+Meeting&F_DocType=Agenda&d-1334500-p=1")
    out.append(f"results page len {len(html)}; rows marker count {html.count('title=\"Meeting\"')}; head {html[:300]!r}")
    docs = eagenda_docs(g, "2026-01-01", "2026-12-31", max_pages=12)
    out.append(f"docs {len(docs)}: {docs[:5]}")
except Exception:
    out.append(traceback.format_exc())
(ROOT / "data/hcfl_probe.txt").write_text("\n".join(out))
print("\n".join(out))
