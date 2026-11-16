"""Build data/fl_agenda.sqlite from the JSON archive (the JSON stays the
source of truth). Tables: items (one row per archived item, with a full-text
index on titles and its project_id), projects (one row per project with a
double-count-free spend total) and committed_projects. The file is published as a GitHub
Release asset by the nightly workflow rather than committed, so it does not
bloat git history. Open it with DB Browser for SQLite, Datasette, or Python.
"""
import glob
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "fl_agenda.sqlite")

COLS = ["entity_id", "government", "client", "body", "meeting_date", "agenda_number", "file_number",
        "title", "max_amount", "flow", "signed_amount", "signal_score", "outgoing_grant", "bypass_competition", "recipient",
        "signals", "keywords", "item_url", "meeting_url", "agenda_pdf", "action", "passed", "tally",
        "source_feed", "first_seen_utc", "last_changed_utc"]


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    db = sqlite3.connect(OUT)
    db.execute("CREATE TABLE items (key TEXT PRIMARY KEY, " + ", ".join(
        f"{c} {'REAL' if c in ('max_amount', 'signal_score', 'signed_amount') else 'INTEGER' if c in ('outgoing_grant', 'bypass_competition') else 'TEXT'}"
        for c in COLS) + ")")
    n = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "archive", "*.json"))):
        for k, r in json.load(open(f)).items():
            row = []
            for c in COLS:
                v = r.get(c)
                if isinstance(v, list):
                    v = ", ".join(map(str, v))
                elif isinstance(v, bool):
                    v = int(v)
                row.append(v)
            db.execute(f"INSERT OR REPLACE INTO items VALUES ({','.join('?' * (len(COLS) + 1))})", [k] + row)
            n += 1
    pj = json.load(open(os.path.join(ROOT, "data", "projects.json")))
    db.execute("ALTER TABLE items ADD COLUMN project_id TEXT")
    db.executemany("UPDATE items SET project_id=? WHERE key=?", [(v, k) for k, v in pj["item_project"].items()])
    db.execute("CREATE TABLE projects (project_id TEXT PRIMARY KEY, government TEXT, name TEXT, items INTEGER, "
               "tracked_spend_total REAL, tracked_receipts_total REAL, total_method TEXT, first_date TEXT, last_date TEXT)")
    db.executemany("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?)",
                   [(k, v["government"], v["name"], v["items"], v["spend_total"], v["receipts_total"], v["total_method"],
                     v["first_date"], v["last_date"]) for k, v in pj["projects"].items()])
    for c in ("entity_id", "meeting_date", "max_amount", "government", "project_id"):
        db.execute(f"CREATE INDEX idx_{c} ON items({c})")
    db.execute("CREATE VIRTUAL TABLE items_fts USING fts5(title, recipient, content='items', content_rowid='rowid')")
    db.execute("INSERT INTO items_fts(rowid, title, recipient) SELECT rowid, title, recipient FROM items")
    cp = json.load(open(os.path.join(ROOT, "config", "committed_projects.json")))["projects"]
    db.execute("CREATE TABLE committed_projects (id TEXT PRIMARY KEY, government TEXT, project TEXT, total_cost REAL, "
               "annual_payment REAL, term_years INTEGER, status TEXT, next_decision TEXT, votes TEXT, sources TEXT)")
    for p in cp:
        db.execute("INSERT INTO committed_projects VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (p["id"], p["government"], p["project"], p.get("total_cost"), p.get("annual_payment"),
                    p.get("term_years"), p.get("status"), p.get("next_decision"),
                    json.dumps(p.get("votes", [])), "\n".join(p.get("sources", []))))
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"sqlite: {n} items, {len(cp)} committed projects, {os.path.getsize(OUT) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
