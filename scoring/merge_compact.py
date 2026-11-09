"""Add the stocks that failed stage 1 (compact rows from screen.js) to scores.json as "Screened out" rows.

Usage: python3 merge_compact.py outdir compact.csv members.txt
"""
import csv, json, sys
out, comp = sys.argv[1], sys.argv[2]
members = sys.argv[3] if len(sys.argv) > 3 else 'members.txt'
names = dict(x.split('|', 1) for x in open(members).read().strip().split(';'))
rows = json.load(open(f'{out}/scores.json')); have = {r['symbol'] for r in rows}
SIG = dict(S='Wait: stretched', D='Buy the dip', F='Wait: still falling', T='Trend buy', A='Avoid: downtrend', W='Watch')
keys = ['chk200', 'chkRsi', 'chkMomentum', 'chkPE', 'chkPEG', 'chkSharpe']
tmpl = {k: None for k in rows[0]}
asof = rows[0]['asOf']; n = len(rows)
f = lambda v: float(v) if v not in ('', None) else None
extra = []
for c in csv.DictReader(open(comp)):
    if c['s'] in have: continue
    b = [x == '1' for x in c['checks']]; rsi, vs, r3, pe, peg, sh = map(f, (c['rsi'], c['vs200'], c['r3m'], c['pe'], c['peg'], c['sharpe']))
    why = []
    if not b[0]: why.append(f'{abs(vs):.0f}% below its 200-DMA')
    if not b[1]: why.append(f'RSI {rsi:.0f} ' + ('overbought' if rsi > 65 else 'and still falling'))
    if not b[2]: why.append(f'3-month return {r3:+.0f}%')
    if not b[3]: why.append('no forward P/E (loss-making)' if not pe or pe <= 0 else f'forward P/E {pe:.0f} above 40')
    if not b[4] and pe and pe > 0: why.append("PEG can't be computed (no positive EPS growth)" if peg is None else f'PEG {peg:.1f} above 2.0')
    if not b[5]: why.append(f'1-year Sharpe {sh:.2f} below 0.5')
    sig = SIG[c['sig']]
    if all(b) and sig not in ('Buy the dip', 'Trend buy', 'Watch'): why.append(f'signal is "{sig}"')
    r = dict(tmpl); r.update(symbol=c['s'], name=names.get(c['s'], c['s']), assetClass='Stock', currency='USD', rsi14=rsi, vsSma200=vs, return3m=r3,
        pe=pe, peg=peg, sharpe=sh, score=round(float(c['score'])), signal=sig, asOf=asof, stage='Screened out',
        checksPassed=sum(b), note='Fails: ' + '; '.join(why) + '.', bull='', bear='', catalyst='', staleTarget=False, turning=None,
        chkEarnings='n/a', **{k: 'pass' if v else 'fail' for k, v in zip(keys, b)})
    extra.append(r)
extra.sort(key=lambda r: -r['score'])
for i, r in enumerate(extra): r['rank'] = n + i + 1
rows += extra
json.dump(rows, open(f'{out}/scores.json', 'w'), separators=(',', ':'))
from collections import Counter; print(len(rows), Counter(r['stage'] for r in rows))
