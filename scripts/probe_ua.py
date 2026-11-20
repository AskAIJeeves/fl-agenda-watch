"""Compare two user agents on sources that time out in the nightly job."""
import json, time, urllib.request
A = {"old": "Mozilla/5.0 (fl-agenda-watch; public records research)",
     "new": "Mozilla/5.0 (compatible; floridaspending.com agenda reader; +https://floridaspending.com)"}
U = ["https://okaloosacountyfl.iqm2.com/Services/RSS.aspx?Feed=Calendar", "https://miamifl.iqm2.com/Services/RSS.aspx?Feed=Calendar",
     "https://fortwaltonbeachcityfl.iqm2.com/Services/RSS.aspx?Feed=Calendar", "https://lakepark-fl.municodemeetings.com/"]
out = {}
for u in U:
    for k, ua in A.items():
        t = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": ua}), timeout=60) as r: res = (r.status, len(r.read()))
        except Exception as e: res = ("err", str(e)[:80])
        out[f"{k} {u[8:40]}"] = [res, round(time.time() - t, 1)]; time.sleep(2)
open("data/probe_ua.json", "w").write(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
