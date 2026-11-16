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
    out.append(f"=== {u}\nstatus {st} {ct} len {len(body)}\n{body[:60000]}")
    links = sorted(set(re.findall(r'(?:href|src)=["\']([^"\']+)', body)))
    out.append("LINKS:\n" + "\n".join(links[:150]))
    apis = sorted(set(re.findall(r'["\'](/[^"\']*(?:api|Api|API|json|Search|search|document|Document)[^"\']*)["\']', body)))
    out.append("API-LIKE:\n" + "\n".join(apis[:80]))
o = re.findall(r'/portal/PTL29560/open/(OBJ\w+)', body if False else out[0])
if o:
    try:
        r = urllib.request.urlopen(urllib.request.Request("https://eagenda.hillsboroughcounty.org/portal/PTL29560/open/" + o[0], headers=UA), timeout=60)
        data = r.read(2000000)
        out.append(f"OPEN {o[0]}: status {r.status} type {r.headers.get('Content-Type')} len {len(data)} head {data[:200]!r}")
    except Exception as e:
        out.append(f"OPEN error {e}")
(ROOT / "data/hcfl_probe.txt").write_text("\n\n".join(out))
print("\n".join(out)[:4000])
