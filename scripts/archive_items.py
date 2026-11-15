"""Permanent archive of every flagged agenda item.

The live feeds keep a rolling window (Legistar: 7 days back; PDFs: 60 days),
so items fall out over time. This script merges each run's items into
data/archive/<year>.json (year of meeting_date, or "undated") and never
deletes anything. Each record keeps first_seen_utc and last_seen_utc;
fields are refreshed from the latest sighting.
"""
import datetime
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ARCH = os.path.join(DATA, "archive")
SOURCES = ["agenda_items.json", "pdf_items.json"]


def key(item):
    ent = item.get("entity_id") or item.get("government") or "?"
    if item.get("client") not in (None, "pdf") and item.get("file_number"):
        return f"{ent}|matter|{item['file_number']}"
    title = " ".join((item.get("title") or "").lower().split())[:300]
    h = hashlib.sha1(title.encode()).hexdigest()[:12]
    doc = hashlib.sha1((item.get("agenda_pdf") or item.get("meeting_url") or "").encode()).hexdigest()[:8]
    return f"{ent}|{item.get('meeting_date') or 'nodate'}|{doc}|{h}"


def year_of(item):
    d = item.get("meeting_date") or ""
    return d[:4] if len(d) >= 4 and d[:4].isdigit() else "undated"


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(ARCH, exist_ok=True)
    books, added, updated = {}, 0, 0
    for src in SOURCES:
        items = load(os.path.join(DATA, src)).get("items", [])
        for it in items:
            y = year_of(it)
            if y not in books:
                books[y] = load(os.path.join(ARCH, f"{y}.json"))
            book, k = books[y], key(it)
            rec = dict(it)
            rec["source_feed"] = src.replace(".json", "")
            if k in book:
                rec["first_seen_utc"] = book[k].get("first_seen_utc", now)
                updated += 1
            else:
                rec["first_seen_utc"] = it.get("found_utc") or now
                added += 1
            rec["last_seen_utc"] = now
            book[k] = rec
    for y, book in books.items():
        path = os.path.join(ARCH, f"{y}.json")
        with open(path, "w") as f:
            f.write("{\n")
            rows = [json.dumps(k) + ": " + json.dumps(book[k], sort_keys=True, ensure_ascii=False)
                    for k in sorted(book)]
            f.write(",\n".join(rows))
            f.write("\n}\n")
    total = sum(len(load(os.path.join(ARCH, f))) for f in os.listdir(ARCH) if f.endswith(".json"))
    print(f"archive: {added} new, {updated} refreshed, {total} total records")


if __name__ == "__main__":
    main()
