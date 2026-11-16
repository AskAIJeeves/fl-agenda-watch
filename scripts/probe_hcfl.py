"""Inspect Hillsborough County's eAgenda portal to learn its structure. Writes data/hcfl_probe.txt."""
import re, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (fl-agenda-watch; public agenda research)"}
out = []
def get(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30)
        return r.status, r.headers.get("Content-Type"), r.read(400000).decode("utf-8", "ignore")
    except Exception as e:
        return None, None, str(e)
for u in ["https://eagenda.hillsboroughcounty.org/portal/PTL29560/search?F_MeetingType=Regular%20BOCC%20Meeting&F_DocType=Agenda",
          "https://eagenda.hillsboroughcounty.org/portal/PTL29560",
          "https://eagenda.hillsboroughcounty.org/"]:
    st, ct, body = get(u)
    out.append(f"=== {u}\nstatus {st} {ct} len {len(body)}\n{body[:3000]}")
    links = sorted(set(re.findall(r'(?:href|src)=["\']([^"\']+)', body)))
    out.append("LINKS:\n" + "\n".join(links[:150]))
    apis = sorted(set(re.findall(r'["\'](/[^"\']*(?:api|Api|API|json|Search|search|document|Document)[^"\']*)["\']', body)))
    out.append("API-LIKE:\n" + "\n".join(apis[:80]))
(ROOT / "data/hcfl_probe.txt").write_text("\n\n".join(out))
print("\n".join(out)[:4000])
