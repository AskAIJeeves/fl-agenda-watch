"""Flag possible duplicates for manual review: the same approval showing up more than once in the archive
(Legistar title and PDF passage of one item, the same money approved again at a later meeting, a deferred item
re-listed, an agenda and its minutes). Nothing is merged or dropped; each item just gets a short list of likely twins.

Rules, within one government:
  same amount   identical dollar amount of $50,000 or more, meetings within 400 days
  similar text  title word overlap (Jaccard) of 0.6 or more, meetings within 400 days
"""
import json, re, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import archive_items

WORD = re.compile(r"[a-z0-9]{3,}")
STOP = set("the and for with from that this approve approval agreement county city board resolution item amount not exceed "
           "authorize execute contract services fiscal year fund funding total department commission".split())
WINDOW = 400

def words(t):
    return {w for w in WORD.findall((t or "").lower()) if w not in STOP}

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def day(v):
    try: return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError): return None

class Index:
    def __init__(self):
        self.by_ent = {}
        for f in sorted((ROOT / "data/archive").glob("*.json")):
            for k, r in archive_items.load(str(f)).items():
                ent = r.get("entity_id")
                if not ent: continue
                self.by_ent.setdefault(ent, []).append(
                    (k, day(r.get("meeting_date")), num(r.get("max_amount")), words(r.get("title")), r.get("meeting_date")))

    def find(self, item_id, ent, meeting_date, amount, title, limit=3):
        d0, amt, w0 = day(meeting_date), num(amount), words(title)
        hits = []
        for k, d, a, w, md in self.by_ent.get(ent, []):
            if k == item_id: continue
            if d0 and d and abs((d - d0).days) > WINDOW: continue
            reasons = []
            if amt and a and amt >= 50000 and abs(a - amt) < 1: reasons.append("same amount")
            if len(w0) >= 4 and len(w) >= 4:
                j = len(w0 & w) / len(w0 | w)
                if j >= 0.6: reasons.append(f"similar text {j:.2f}")
            if reasons:
                hits.append({"id": k, "meeting_date": md, "reason": ", ".join(reasons)})
        hits.sort(key=lambda h: (-len(h["reason"].split(",")), h["meeting_date"] or ""))
        return hits[:limit]

def label(hits, meeting_date=None):
    """One-line text for the review sheet: matches at OTHER meetings only (same money approved or listed again).
    Same-meeting twins are usually backup pages of one agenda packet; the sheet check against existing rows covers those."""
    other, dates = [], set()
    for h in hits:
        if h["meeting_date"] == meeting_date or h["meeting_date"] in dates: continue
        dates.add(h["meeting_date"]); other.append(h)
    return "; ".join(f'{h["meeting_date"] or "undated"} ({h["reason"]}): {h["id"]}' for h in other) or None

def enrich_backlog():
    """Add possible_duplicates to data/backlog_candidates.json in place (order and n unchanged)."""
    p = ROOT / "data/backlog_candidates.json"
    d = json.loads(p.read_text()); idx = Index(); n = 0
    ents = {}
    for f in sorted((ROOT / "data/archive").glob("*.json")):
        for k, r in archive_items.load(str(f)).items():
            ents[k] = (r.get("entity_id"), r.get("title"))
    for x in d["items"]:
        ent, title = ents.get(x["id"], (None, x.get("text")))
        x["possible_duplicates"] = idx.find(x["id"], ent, x.get("meeting_date"), x.get("amount"), title)
        x["possible_duplicate_label"] = label(x["possible_duplicates"], x.get("meeting_date"))
        n += bool(x["possible_duplicate_label"])
    p.write_text(json.dumps(d, indent=1))
    print(f"backlog: {n} of {len(d['items'])} items have a possible duplicate", file=sys.stderr)

if __name__ == "__main__":
    enrich_backlog()
