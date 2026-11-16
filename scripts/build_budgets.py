"""Budget size for every covered government, from the Florida Legislature's
Office of Economic and Demographic Research (EDR) compilation of the
Annual Financial Reports local governments file with the Department of
Financial Services. Most recent fiscal year in each workbook.

Writes data/budgets.json: {entity_id: {name, fiscal_year, general_fund_expenditures,
total_expenditures, population, source_url}}. Run occasionally (the data are annual).
Duval County's figures are reported under the City of Jacksonville.
"""
import io
import json
import re
import urllib.request
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.edr.state.fl.us/Content/local-government/data/revenues-expenditures/"
UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public finance research)"}


def governments():
    g = json.loads((ROOT / "config/governments.json").read_text())["governments"]
    p = json.loads((ROOT / "config/pdf_sources.json").read_text())
    out = {x["entity_id"]: x["name"] for x in g}
    for v in p.values():
        if isinstance(v, list):
            out.update({x["entity_id"]: x["name"] for x in v if isinstance(x, dict) and x.get("entity_id")})
    return out


def url_for(eid, name):
    n = re.sub(r"\(.*?\)", "", name).replace("Miami-Dade", "Miami Dade").replace("St.", "St").strip()
    if eid.startswith("c-"):
        return BASE + "cntyfiscal/" + re.sub(r"[^a-z]", "", n.lower()) + "expenditures.xlsx"
    return BASE + "munifiscal/" + re.sub(r"[^a-z]", "", n.lower()) + "expenditures.xlsx"


def parse(data):
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.worksheets[0]                      # sheets are fiscal years, newest first
    rows = list(ws.iter_rows(values_only=True))
    hdr = next(r for r in rows if r and any(str(v).strip() == "General" for v in r if v))
    col = {str(v).strip(): i for i, v in enumerate(hdr) if v}
    gcol = col["General"]
    tcol = [i for i, v in enumerate(hdr) if v and "Total" in str(v)][-1]
    tot = next(r for r in rows if r and r[0] and str(r[0]).startswith("Total - All"))
    funds = {k: tot[col[h]] for k, h in (("special_revenue", "Special Revenue"), ("debt_service", "Debt Service"),
             ("capital_projects", "Capital Projects"), ("enterprise", "Enterprise"), ("internal_service", "Internal Service"))
             if h in col}
    pop = None
    for r in rows:
        for i, v in enumerate(r or []):
            if v and "Population" in str(v):
                pop = next((x for x in r[i + 1:] if isinstance(x, (int, float))), None)
    return {"fiscal_year": ws.title, "general_fund_expenditures": tot[gcol], "total_expenditures": tot[tcol],
            "population": pop, "fund_expenditures": {"general": tot[gcol], **funds}}


def main():
    out, missing = {}, []
    for eid, name in sorted(governments().items()):
        u = url_for(eid, name)
        try:
            data = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read()
            out[eid] = {"name": name, **parse(data), "source_url": u}
        except Exception as e:
            missing.append({"entity_id": eid, "name": name, "url": u, "error": str(e)[:120]})
    (ROOT / "data/budgets.json").write_text(json.dumps({"source": "Florida EDR, compiled from DFS Annual Financial Reports",
                                                        "governments": out, "missing": missing}, indent=1))
    print(f"budgets: {len(out)} found, {len(missing)} missing")
    for m in missing:
        print("missing", m["name"], m["url"].rsplit("/", 1)[-1], m["error"][:60])


if __name__ == "__main__":
    main()
