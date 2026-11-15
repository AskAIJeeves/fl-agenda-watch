"""Check that Legistar gateway links resolve to the item page."""
import json, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
out = {}
for client in ["fortlauderdale", "jaxcityc", "broward"]:
    try:
        ms = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://webapi.legistar.com/v1/{client}/matters?$top=1&$orderby=MatterId%20desc", headers=UA), timeout=40).read())
        mid = ms[0]["MatterId"]; u = f"https://{client}.legistar.com/gateway.aspx?M=L&ID={mid}"
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40); b = r.read(5000).decode("utf-8", "replace")
        out[client] = [u, r.status, r.geturl(), "LegislationDetail" in r.geturl() or "Legislation" in b[:5000], ms[0].get("MatterTitle", "")[:80]]
    except Exception as e:
        out[client] = str(e)[:200]
(ROOT / "data/endpoint_probe.json").write_text(json.dumps(out, indent=1))
