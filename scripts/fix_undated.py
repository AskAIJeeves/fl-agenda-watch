"""One-off: give undated PDF-reader items the meeting date found in their meeting title
(e.g. 'City Commission Meeting - May 12, 2026') and move them to their month archive file."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import archive_items as A

MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
def tdate(t):
    t = str(t or "")
    try:
        m = re.search(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d\d)\b", t)
        if m: return f"{int(m[3]):04d}-{MON[m[1][:3].lower()]:02d}-{int(m[2]):02d}"
        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", t)
        if m and 1 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= 31: return f"{int(m[3]):04d}-{int(m[1]):02d}-{int(m[2]):02d}"
    except (ValueError, KeyError): pass
    return None

und_p = ROOT / "data/archive/undated.json"
und = json.loads(und_p.read_text())
books, moved = {}, 0
for k in list(und.keys()):
    rec = und[k]
    d = tdate(rec.get("body"))
    if not d: continue
    rec = dict(rec, meeting_date=d, prior_key=k)
    y = d[:7]
    if y not in books: books[y] = A.load(str(ROOT / f"data/archive/{y}.json"))
    nk = A.key(rec)
    books[y].setdefault(nk, rec)
    del und[k]; moved += 1
for y, b in books.items():
    (ROOT / f"data/archive/{y}.json").write_text("{\n" + ",\n".join(json.dumps(k) + ": " + json.dumps(b[k], sort_keys=True, ensure_ascii=False) for k in sorted(b)) + "\n}\n")
und_p.write_text("{\n}\n" if not und else json.dumps(und))
pi_p = ROOT / "data/pdf_items.json"
pi = json.loads(pi_p.read_text()); n2 = 0
for it in pi["items"]:
    if not it.get("meeting_date"):
        d = tdate(it.get("body"))
        if d: it["meeting_date"] = d; n2 += 1
pi_p.write_text(json.dumps(pi, indent=1))
print("archive moved", moved, "left undated", len(und), "| pdf_items dated", n2, "| month files touched", len(books))
