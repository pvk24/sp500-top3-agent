"""Build raw.json (the input to score.py) from the browser's stage-1 and stage-2 output.

Usage: python3 build_raw.py members.txt full.csv outlook.json raw.json [asof-ISO]
  members.txt  SYMBOL|Name entries separated by ';' (from the Wikipedia membership step)
  full.csv     stage-1 rows for the stocks that passed the six price/valuation checks (from screen.js), plus QQQ
  outlook.json stage-2 analyst data keyed by symbol (from stage2.js); these symbols become the shortlist
"""
import csv, datetime as dt, json, sys

members, full, outlook, out = sys.argv[1:5]
asof = sys.argv[5] if len(sys.argv) > 5 else dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
names = dict(x.split('|', 1) for x in open(members).read().strip().split(';'))
ol = json.load(open(outlook))
items = []
for r in csv.DictReader(open(full)):
    if r['s'] in ('QQQ', 'SPY'): continue
    it = {k: (float(v) if v != '' else None) for k, v in r.items() if k != 's'}
    it.update(s=r['s'], name=names.get(r['s'], r['s']), cls='Stock', ccy='USD', stage='Shortlist' if r['s'] in ol else 'Screened out')
    if r['s'] in ol: it['outlook'] = ol[r['s']]
    items.append(it)
json.dump({"asof": asof, "source": "Yahoo Finance; universe = S&P 500 (Wikipedia list)", "items": items}, open(out, 'w'), indent=1)
print(f'{len(items)} items, {sum(i["stage"] == "Shortlist" for i in items)} shortlisted')
