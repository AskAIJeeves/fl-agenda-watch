"""Apply data/review_patch.json (written by the daily export task) to data/review_export.json.

Patch format: {"rows": [row, ...], "removed": [item_id, ...], "full": false}
  rows     new or changed rows, matched on item_id (a changed row replaces the stored one)
  removed  item_ids no longer in the sheet (deleted duplicates)
  full     true when "rows" is the whole sheet: the export is replaced instead of patched
The patch file is deleted after it is applied.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P, X = ROOT / "data/review_patch.json", ROOT / "data/review_export.json"


def main():
    if not P.exists():
        print("no patch"); return
    patch = json.loads(P.read_text())
    store = {} if patch.get("full") or not X.exists() else {r["item_id"]: r for r in json.loads(X.read_text())["rows"]}
    for r in patch.get("rows", []):
        if r.get("item_id"):
            store[r["item_id"]] = r
    for k in patch.get("removed", []):
        store.pop(k, None)
    X.write_text(json.dumps({"rows": list(store.values())}, indent=1))
    P.unlink()
    print(f"export rows: {len(store)} (+{len(patch.get('rows', []))} upserted, -{len(patch.get('removed', []))} removed)")


if __name__ == "__main__":
    main()
