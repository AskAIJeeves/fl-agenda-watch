"""Find Pasco County FL's agenda system."""
import json, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
out = {}
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40); b = r.read(200000)
        return [r.status, r.geturl(), b[:300].decode("utf-8", "replace")]
    except urllib.error.HTTPError as e: return [e.code, u, ""]
    except Exception as e: return [None, u, str(e)[:150]]
for u in ["https://mypas.co/BCCAgenda", "http://mypas.co/BCCAgenda", "https://www.pascocountyfl.net/AgendaCenter", "https://www.pascocountyfl.gov/AgendaCenter"]:
    out[u] = get(u)
for t in ["pascocountyfl", "pascofl", "pascocounty", "pascoco", "pascocountybcc", "pasco"]:
    out["civicclerk:" + t] = get(f"https://{t}.api.civicclerk.com/v1/Events?$top=2")
(ROOT / "data/endpoint_probe.json").write_text(json.dumps(out, indent=1))
