"""Dump the layout of sample EDR local government revenue/expenditure workbooks
(edr.state.fl.us) to data/edr_sample.txt so a parser can be written."""
import io, urllib.request
from pathlib import Path
import openpyxl
ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.edr.state.fl.us/Content/local-government/data/revenues-expenditures/"
out = []
for f in ["munifiscal/dunedinexpenditures.xlsx", "munifiscal/jacksonvilleexpenditures.xlsx",
          "cntyfiscal/pinellascountyexpenditures.xlsx", "munifiscal/dunedinrevenues.xlsx"]:
    try:
        data = urllib.request.urlopen(urllib.request.Request(BASE + f, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        out.append(f"=== {f}: sheets {wb.sheetnames}")
        for ws in wb.worksheets[:3]:
            out.append(f"--- sheet {ws.title}")
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= 45: break
                out.append(" | ".join("" if v is None else str(v)[:28] for v in row[:16]))
    except Exception as e:
        out.append(f"=== {f}: ERROR {e}")
(ROOT / "data/edr_sample.txt").write_text("\n".join(out))
print("\n".join(out[:20]))
