"""Dry run of the new readers (BoardDocs, Swagit, granicusideas) without writing any data."""
import json, sys
from collections import defaultdict
from datetime import datetime, timezone
sys.path.insert(0, "scripts")
import fetch_pdf_agendas as f

cfg = json.load(open("config/pdf_sources.json"))
only = {k: cfg[k] for k in ("boarddocs", "swagit", "granicusideas")}
run = {"max_new_pdfs_per_run": cfg["max_new_pdfs_per_run"], "max_pages_per_pdf": cfg["max_pages_per_pdf"], "meeting_skip": cfg.get("meeting_skip"), **only}
store, seen, debug = {"items": []}, {}, {}
f.scan_platforms(run, store, seen, debug, datetime.now(timezone.utc))
for k, v in debug.items():
    if any(k.endswith(":" + p) for p in only):
        print(k, json.dumps({x: v[x] for x in v if x != "scanned"})[:300])
        for s in v["scanned"][:4]: print("   ", s)
by = defaultdict(list)
for it in store["items"]: by[it["government"]].append(it)
print("items", len(store["items"]))
for g, its in by.items():
    print("==", g, len(its))
    for it in sorted(its, key=lambda x: -(x.get("max_amount") or 0))[:3]:
        print("   ", it["meeting_date"], it.get("max_amount"), it["title"][:220], "|", it["agenda_pdf"])
