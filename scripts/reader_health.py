"""Reader health report: for every configured government, what its reader produced
in the last 90 days. Writes data/reader_health.json and prints a ranked summary."""
import json, glob, collections
from datetime import date, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def L(p):
    d = json.load(open(p)); return d if isinstance(d, list) else (d['items'] if 'items' in d else list(d.values()))

today = date.today(); c90 = (today - timedelta(days=90)).isoformat()
status = json.load(open(ROOT / 'data/agenda_status.json'))['governments']
arch = []
for f in glob.glob(str(ROOT / 'data/archive/*.json')):
    arch += [a for a in L(f) if isinstance(a, dict)]
by = collections.defaultdict(list)
for a in arch:
    by[a.get('entity_id')].append(a)
pdf = json.load(open(ROOT / 'config/pdf_sources.json'))
src = {}
for plat, ents in pdf.items():
    if isinstance(ents, list):
        for e in ents:
            if isinstance(e, dict) and e.get('entity_id'):
                src[e['entity_id']] = (e.get('name') or e['entity_id'], plat)
for k, v in status.items():
    src.setdefault(k, (v.get('name'), 'api:' + (v.get('client') or '?')))
site = json.load(open(ROOT / 'site/data/items.json')); site = site['items'] if isinstance(site, dict) else site
sitec = collections.Counter(i['government'] for i in site)
rows = []
for eid, (name, plat) in src.items():
    its = by.get(eid, [])
    recent = [a for a in its if (a.get('meeting_date') or '') >= c90]
    undated = [a for a in its if not a.get('meeting_date')]
    amt = [a for a in recent if a.get('max_amount')]
    last = max((a.get('meeting_date') or '' for a in its), default='')
    gov = (its[0].get('government') if its else name) or name
    st = status.get(eid, {}).get('status')
    if not its: verdict = 'dead'
    elif not recent and last < c90: verdict = 'stale'
    elif len(recent) < 10: verdict = 'thin'
    elif len(amt) / max(len(recent), 1) < 0.15: verdict = 'no_amounts'
    elif len(undated) > len(recent): verdict = 'undated_heavy'
    else: verdict = 'ok'
    rows.append({'id': eid, 'government': gov, 'platform': plat, 'status': st, 'items_90d': len(recent),
                 'with_amount_90d': len(amt), 'undated_total': len(undated), 'last_meeting': last,
                 'on_site': sitec.get(gov, 0), 'verdict': verdict})
order = ['dead', 'stale', 'thin', 'no_amounts', 'undated_heavy', 'ok']
rows.sort(key=lambda r: (order.index(r['verdict']), r['government'] or ''))
(ROOT / 'data/reader_health.json').write_text(json.dumps({'generated': today.isoformat(), 'rows': rows}, indent=1))
cnt = collections.Counter(r['verdict'] for r in rows)
print(len(rows), dict(cnt))
for r in rows:
    if r['verdict'] != 'ok':
        print(f"{r['verdict']:13} {str(r['government'])[:34]:34} {r['platform'][:16]:16} 90d={r['items_90d']:4} amt={r['with_amount_90d']:4} undated={r['undated_total']:4} last={r['last_meeting']} site={r['on_site']}")
