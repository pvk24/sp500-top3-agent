"""Daily run without a browser: collect, score, backtest and save everything to data/live/.

Runs on GitHub Actions (see .github/workflows/daily.yml) or anywhere with Python 3.9+ and `requests`.
It does what browser/members.js, screen.js, stage2.js and backtest.js do in a browser tab, with the same rules,
then calls scoring/build_raw.py, scoring/score.py and scoring/merge_compact.py.

Usage: python3 collector/run_daily.py [--date YYYY-MM-DD]
Writes data/live/: scores.json, prices.json, track.json, backtest.json, backtest_summary.json, state.json, run.json
State (the monthly lock and the pick log) is kept in data/live/state.json between runs.
"""
import csv, datetime as dt, html.parser, json, math, os, re, subprocess, sys, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, 'data', 'live')
WORK = os.path.join(ROOT, 'work')
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PE_MAX, PEG_MAX, SHARPE_MIN = 40, 2.0, 1.0   # keep in step with scoring/score.py
SHORTLIST = 15
BENCH = 'SPY'
BT_START = '2023-11-01'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
      'Accept': 'application/json,text/plain,*/*', 'Accept-Language': 'en-US,en;q=0.9'}

S = requests.Session(); S.headers.update(UA)
errs = []


def say(*a):
    print(dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S'), *a, flush=True)


def get(url, tries=3, as_json=True):
    for k in range(tries):
        try:
            r = S.get(url, timeout=15)
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f'HTTP {r.status_code}')
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception as e:  # retry with backoff
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


# ---------- membership ----------
class _Table(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(); self.on = False; self.rows = []; self.row = None; self.cell = None; self.depth = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'table' and a.get('id') == 'constituents': self.on = True; self.depth = 1; return
        if not self.on: return
        if tag == 'table': self.depth += 1
        elif tag == 'tr': self.row = []
        elif tag in ('td', 'th') and self.row is not None: self.cell = []
    def handle_endtag(self, tag):
        if not self.on: return
        if tag == 'table':
            self.depth -= 1
            if self.depth == 0: self.on = False
        elif tag in ('td', 'th') and self.cell is not None and self.row is not None:
            self.row.append(''.join(self.cell).strip()); self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row = None
    def handle_data(self, d):
        if self.on and self.cell is not None: self.cell.append(d)


def members():
    p = _Table(); p.feed(get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', as_json=False))
    out = []
    for r in p.rows[1:]:
        if len(r) < 2: continue
        sym = r[0].strip().replace('.', '-')
        if sym and sym != 'GOOGL': out.append((sym, r[1].strip()))
    return out


# ---------- stage 1 (same maths as browser/screen.js) ----------
def R(x, n=4):
    return None if x is None or not math.isfinite(x) else round(x, n)

def sma(a, n): return sum(a[-n:]) / n if len(a) >= n else None
def ret(a, n): return a[-1] / a[-1 - n] - 1 if len(a) > n else None
def clip(x): return max(0.0, min(100.0, x))

def rsi(a, n=14):
    if len(a) < 20: return None
    g = l = 0.0
    for i in range(1, n + 1):
        d = a[i] - a[i - 1]
        if d > 0: g += d
        else: l -= d
    g /= n; l /= n
    for i in range(n + 1, len(a)):
        d = a[i] - a[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n; l = (l * (n - 1) + max(-d, 0)) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)


def chart(sym):
    """5 years of daily data: (dates, closes, adjusted closes, live price)."""
    j = get(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d&events=div,split')
    r = j['chart']['result'][0]
    q = r['indicators']['quote'][0]['close']
    adj = (r['indicators'].get('adjclose') or [{}])[0].get('adjclose') or q
    dates = [dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%Y-%m-%d') for t in r['timestamp']]
    return dates, q, adj, r['meta'].get('regularMarketPrice')


def stage1_row(sym, closes, price):
    c = [x for x in closes if x is not None]
    yr = c[-252:]
    lr = [math.log(c[-61:][i] / c[-61:][i - 1]) for i in range(1, len(c[-61:]))]
    mu = sum(lr) / len(lr)
    sharpe = None
    if len(c) >= 253:
        d = [c[-253:][i] / c[-253:][i - 1] - 1 for i in range(1, 253)]
        m = sum(d) / len(d); sd = math.sqrt(sum((x - m) ** 2 for x in d) / (len(d) - 1))
        sharpe = R((m * 252 - 0.04) / (sd * math.sqrt(252)), 3)
    row = {'s': sym, 'price': R(price), 'prevClose': R(c[-2]), 'n': min(len(c), 295),
           'r1w': R(ret(c, 5)), 'r1m': R(ret(c, 21)), 'r3m': R(ret(c, 63)), 'r6m': R(ret(c, 126)), 'r12m': R(ret(c, 252)),
           'mom12_1': R(c[-22] / c[-253] - 1 if len(c) > 252 else None), 'sma20': R(sma(c, 20)), 'sma50': R(sma(c, 50)), 'sma200': R(sma(c, 200)),
           'rsi14': R(rsi(c[-120:]), 2), 'rsi14_5d': R(rsi(c[-125:-5]), 2), 'hi52': R(max(yr)), 'lo52': R(min(yr)),
           'vol60': R(math.sqrt(sum((x - mu) ** 2 for x in lr) / (len(lr) - 1)) * math.sqrt(252)), 'sharpe1y': sharpe}
    step = max(1, len(yr) // 52)
    spark = [R(x, 2) for i, x in enumerate(yr) if i % step == 0] + [R(c[-1], 2)]
    return row, spark


def crumb():
    try: S.get('https://fc.yahoo.com', timeout=20)
    except Exception: pass
    return get('https://query1.finance.yahoo.com/v1/test/getcrumb', as_json=False).strip()


def valuation(out, syms, cr):
    for i in range(0, len(syms), 50):
        try:
            j = get('https://query2.finance.yahoo.com/v7/finance/quote?symbols=' + ','.join(syms[i:i + 50]) +
                    '&fields=forwardPE,epsForward,epsCurrentYear,epsTrailingTwelveMonths&crumb=' + requests.utils.quote(cr))
            for q in j['quoteResponse']['result']:
                if q['symbol'] in out:
                    out[q['symbol']].update(fwdPE=R(q.get('forwardPE')), epsFwd=R(q.get('epsForward')),
                                            epsCY=R(q.get('epsCurrentYear')), epsTTM=R(q.get('epsTrailingTwelveMonths')))
        except Exception as e:
            errs.append(f'valuation batch {i}: {e}')


def screen(out, syms):
    compact, full = [], []
    for s in syms:
        it = out[s]
        if not it.get('sma200') or not it.get('hi52') or it.get('mom12_1') is None: continue
        p, rsiv = it['price'], it['rsi14']; rsi5 = it['rsi14_5d'] if it['rsi14_5d'] is not None else rsiv
        vs50, vs200 = p / it['sma50'] - 1, p / it['sma200'] - 1
        vs20 = p / it['sma20'] - 1 if it.get('sma20') else 0; off = p / it['hi52'] - 1
        r3m, m121 = it['r3m'] or 0, it['mom12_1'] or 0
        k = max(0.5, min(1.5, 0.25 / it['vol60'])) if it.get('vol60') else 1
        trend = clip(50 + 250 * vs200 * k); mom = 0.5 * clip(50 + 166.7 * r3m * k) + 0.5 * clip(50 + 125 * m121 * k)
        entry = 0.5 * clip((70 - rsiv) / 40 * 100) + 0.5 * clip(30 + 280 * -off * k)
        pe, ef, ec, et = it.get('fwdPE'), it.get('epsFwd'), it.get('epsCY'), it.get('epsTTM')
        base = ec if ec and ec > 0 else (et if et and et > 0 else None)
        growth = ef / base - 1 if ef and base else None
        peg = pe / (100 * growth) if pe and pe > 0 and growth and growth > 0 else None
        val = 0.5 * (clip((PE_MAX - pe) / 30 * 100) if pe and pe > 0 else 0) + 0.5 * (clip((2.5 - peg) / 2 * 100) if peg is not None else 0)
        score = (0.30 * trend + 0.30 * mom + 0.15 * entry + 0.15 * val) / 0.90
        turning = p > (it.get('sma20') or p) or rsiv > rsi5 + 3
        pull = rsiv < 40 or off <= -0.15
        sig = 'S' if rsiv > 70 else ('D' if turning else 'F') if pull and vs200 > 0 else 'T' if vs50 > 0 and vs200 > 0 and 45 <= rsiv <= 70 else 'A' if vs200 < -0.03 and r3m < 0 else 'W'
        ck = [vs200 > 0, (30 <= rsiv <= 65) or (rsiv < 30 and rsiv > rsi5), r3m > 0 or (m121 > 0 and vs20 > 0),
              pe is not None and 0 < pe <= PE_MAX, peg is not None and peg <= PEG_MAX, it.get('sharpe1y') is not None and it['sharpe1y'] >= SHARPE_MIN]
        f = lambda v, n: '' if v is None else f'{v:.{n}f}'
        compact.append([s, f'{score:.1f}', f'{rsiv:.1f}', f'{100 * vs200:.1f}', f'{100 * r3m:.1f}', f(pe, 1), f(peg, 2), f(it.get('sharpe1y'), 2), ''.join(str(int(x)) for x in ck), sig])
        if all(ck) and sig in 'DTW': full.append(s)
    return compact, full


# ---------- stage 2 (same fields as browser/stage2.js) ----------
def outlook(sym, cr):
    j = get(f'https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules=financialData,earningsTrend,defaultKeyStatistics,calendarEvents&crumb=' + requests.utils.quote(cr))
    Q = j['quoteSummary']['result'][0]
    rw = lambda x: x.get('raw') if isinstance(x, dict) else None
    f = Q.get('financialData', {}); ny = next((t for t in Q.get('earningsTrend', {}).get('trend', []) if t.get('period') == '+1y'), {})
    et, er = ny.get('epsTrend') or {}, ny.get('epsRevisions') or {}
    ed = ((Q.get('calendarEvents') or {}).get('earnings') or {}).get('earningsDate') or []
    return {'targetMean': rw(f.get('targetMeanPrice')), 'recMean': rw(f.get('recommendationMean')), 'analysts': rw(f.get('numberOfAnalystOpinions')),
            'fwdPE': rw((Q.get('defaultKeyStatistics') or {}).get('forwardPE')), 'epsNY': rw(et.get('current')), 'epsNY90': rw(et.get('90daysAgo')),
            'revUp30': rw(er.get('upLast30days')) or 0, 'revDown30': rw(er.get('downLast30days')) or 0, 'nextEarnings': ed[0].get('fmt') if ed else None}


# ---------- backtest (same rules as browser/backtest.js) ----------
def backtest(adj_by_sym, bench_dates):
    D = bench_dates
    syms = [s for s in adj_by_sym if s != BENCH]
    C = {}
    for s, m in adj_by_sym.items():
        last = None; col = []
        for d in D:
            v = m.get(d)
            if v is not None: last = v
            col.append(last)
        C[s] = col
    RS = {}
    for s in syms:
        a = C[s]; r = [None] * len(D); g = l = 0.0
        st = next((i for i, v in enumerate(a) if v is not None), -1)
        if st >= 0:
            for i in range(st + 1, len(a)):
                ch = a[i] - a[i - 1]; up, dn = max(ch, 0), max(-ch, 0)
                if i - st <= 14:
                    g += up / 14; l += dn / 14
                    if i - st == 14: r[i] = 100 if l == 0 else 100 - 100 / (1 + g / l)
                else:
                    g = (g * 13 + up) / 14; l = (l * 13 + dn) / 14; r[i] = 100 if l == 0 else 100 - 100 / (1 + g / l)
        RS[s] = r

    def smai(a, i, n):
        if i < n - 1 or a[i - n + 1] is None: return None
        return sum(a[i - n + 1:i + 1]) / n

    def ev(s, i):
        a = C[s]
        if i < 260 or a[i - 252] is None: return None
        p = a[i]; s20, s50, s200 = smai(a, i, 20), smai(a, i, 50), smai(a, i, 200)
        if not s200: return None
        rv = RS[s][i]; r5 = RS[s][i - 5] if RS[s][i - 5] is not None else rv
        hi = max(a[i - 251:i + 1]); r3m = p / a[i - 63] - 1; m121 = a[i - 21] / a[i - 252] - 1
        lr = [math.log(a[k] / a[k - 1]) for k in range(i - 59, i + 1)]; mu = sum(lr) / 60
        vol = math.sqrt(sum((y - mu) ** 2 for y in lr) / 59) * math.sqrt(252)
        k = max(0.5, min(1.5, 0.25 / vol)) if vol else 1
        vs50, vs200, off = p / s50 - 1, p / s200 - 1, p / hi - 1
        trend = clip(50 + 250 * vs200 * k); mom = 0.5 * clip(50 + 166.7 * r3m * k) + 0.5 * clip(50 + 125 * m121 * k)
        entry = 0.5 * clip((70 - rv) / 40 * 100) + 0.5 * clip(30 + 280 * -off * k)
        score = (0.30 * trend + 0.30 * mom + 0.15 * entry) / 0.75; turning = rv > r5
        if rv > 70: sig = 'S'
        elif (rv < 40 or off <= -0.15) and vs200 > 0: sig = 'D' if turning else 'F'
        elif vs50 > 0 and vs200 > 0 and 45 <= rv <= 70: sig = 'T'
        elif vs200 < -0.03 and r3m < 0: sig = 'A'
        else: sig = 'W'
        ok = vs200 > 0 and ((30 <= rv <= 65) or (rv < 30 and turning)) and (r3m > 0 or (m121 > 0 and p > s20)) and sig in 'DTW'
        return score, ok

    start = next(i for i, d in enumerate(D) if d >= BT_START)
    month_idx = [i for i in range(start, len(D)) if i == start or D[i][:7] != D[i - 1][:7]]
    week_idx = list(range(start, len(D), 5))

    def run(rebal, pick):
        rs = set(rebal); hold = []; eq = peak = 1.0; dd = 0.0; curve = {start: (1.0, '')}
        for i in range(start, len(D)):
            if i > start:
                rets = [C[s][i] / C[s][i - 1] - 1 for s in hold if C[s][i] is not None and C[s][i - 1]]
                rets = [x for x in rets if math.isfinite(x)]
                eq *= 1 + (sum(rets) / len(hold) if rets else 0); peak = max(peak, eq); dd = min(dd, eq / peak - 1)
            if i in rs:
                if i > start: curve[i] = (eq, ' '.join(hold))
                hold = pick(i)
        curve[len(D) - 1] = (eq, ' '.join(hold))
        return eq, dd, curve

    def top(n):
        def f(i):
            sc = [(s, ev(s, i)) for s in syms]
            sc = [(s, e[0]) for s, e in sc if e and e[1]]
            return [s for s, _ in sorted(sc, key=lambda x: -x[1])[:n]]
        return f

    ew_pick = lambda i: [s for s in syms if C[s][i] is not None and C[s][i - 1] is not None]
    strat, wk, t10, ew, bm = run(month_idx, top(3)), run(week_idx, top(3)), run(month_idx, top(10)), run(month_idx, ew_pick), run(month_idx, lambda i: [BENCH])
    rows = []
    for j, i in enumerate(month_idx + [len(D) - 1]):
        rows.append({'date': D[i], 'strategy': round(strat[2][i][0], 4) if j else 1, 'watchlist': round(ew[2][i][0], 4) if j else 1,
                     'spy': round(bm[2][i][0], 4) if j else 1, 'picks': strat[2][i][1] if j else ''})
    pct = lambda x: round(100 * x)
    summary = [{'variant': v, 'total': pct(r[0] - 1), 'maxDD': pct(r[1]), 'current': c} for v, r, c in [
        ('Top 3, all price checks, held a month (used now)', strat, True), ('Same, rebalanced weekly', wk, False),
        ('Top 10 instead of top 3, monthly', t10, False), ('Equal-weight all current members', ew, False), (f'{BENCH} buy and hold', bm, False)]]
    return rows, summary


# ---------- main ----------
def main():
    today = sys.argv[sys.argv.index('--date') + 1] if '--date' in sys.argv else dt.datetime.now(IST).strftime('%Y-%m-%d')
    os.makedirs(LIVE, exist_ok=True); os.makedirs(WORK, exist_ok=True)
    state_path = os.path.join(LIVE, 'state.json')
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    lock = state.get('lock') or {}
    month = today[:7]

    say('fetching membership')
    mem = members()
    say('members', len(mem))
    if len(mem) < 490: raise SystemExit(f'Only {len(mem)} S&P 500 members found; stopping without publishing.')
    names = dict(mem)
    open(os.path.join(WORK, 'members.txt'), 'w').write(';'.join(f'{s}|{n}' for s, n in mem))

    out, spark, adj = {}, {}, {}
    n_done = 0
    spy_close = None
    for s in [m[0] for m in mem] + [BENCH]:
        try:
            dates, closes, adjc, price = chart(s)
            adj[s] = {d: v for d, v in zip(dates, adjc) if v is not None}
            if s != BENCH:
                out[s], spark[s] = stage1_row(s, closes, price)
            else:
                spy_dates, spy_close = dates, price
        except Exception as e:
            errs.append(f'{s}: {e}')
        n_done += 1
        if n_done % 25 == 0: say('charts', n_done, 'ok', len(out), 'errors', len(errs), errs[-1] if errs else '')
        if n_done == 12 and len(out) == 0: raise SystemExit(f'First 12 price requests all failed; stopping. Errors: {errs[:3]}')
        time.sleep(0.05)
    if spy_close is None: raise SystemExit(f'No {BENCH} price; stopping without publishing.')
    if len(out) < 450: raise SystemExit(f'Price data for only {len(out)} stocks; stopping without publishing. Errors: {errs[:5]}')
    say('getting crumb')
    cr = crumb()
    say('valuation')
    syms = list(out)
    valuation(out, syms, cr)
    compact, full = screen(out, syms)

    cols = ['s', 'price', 'prevClose', 'n', 'r1w', 'r1m', 'r3m', 'r6m', 'r12m', 'mom12_1', 'sma20', 'sma50', 'sma200', 'rsi14', 'rsi14_5d',
            'hi52', 'lo52', 'vol60', 'sharpe1y', 'fwdPE', 'epsFwd', 'epsCY', 'epsTTM']
    locked = lock.get('picks', []) if lock.get('month') == month else []
    score_of = {r[0]: float(r[1]) for r in compact}
    short = sorted(full, key=lambda s: -score_of[s])[:SHORTLIST]
    short += [s for s in locked if s not in short and s in out]
    rows_for = full + [s for s in locked if s not in full and s in out]
    with open(os.path.join(WORK, 'full.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(cols)
        for s in rows_for: w.writerow(['' if out[s].get(c) is None else out[s].get(c) for c in cols])
    with open(os.path.join(WORK, 'compact.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['s', 'score', 'rsi', 'vs200', 'r3m', 'pe', 'peg', 'sharpe', 'checks', 'sig']); w.writerows(compact)

    say('screened', len(compact), 'passed six', len(full), 'errors', len(errs))
    ol = {}
    for s in short:
        try: ol[s] = outlook(s, cr)
        except Exception as e: errs.append(f'{s} outlook: {e}')
        time.sleep(0.2)
    json.dump(ol, open(os.path.join(WORK, 'outlook.json'), 'w'))

    say('outlook done', len(ol), '; scoring')
    py, sc = sys.executable, os.path.join(ROOT, 'scoring')
    asof = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    subprocess.run([py, f'{sc}/build_raw.py', f'{WORK}/members.txt', f'{WORK}/full.csv', f'{WORK}/outlook.json', f'{WORK}/raw.json', asof], check=True)
    json.dump([], open(f'{WORK}/empty.json', 'w')); json.dump(lock, open(f'{WORK}/lock.json', 'w'))
    subprocess.run([py, f'{sc}/score.py', f'{WORK}/raw.json', f'{WORK}/empty.json', f'{WORK}/out', '-', f'{WORK}/lock.json'], check=True, stdout=subprocess.DEVNULL)
    new_lock = json.load(open(f'{WORK}/out/lock.json'))
    raw = json.load(open(f'{WORK}/raw.json'))
    for it in raw['items']:
        if it['s'] in new_lock['picks']: it['spark'] = spark.get(it['s'])
    json.dump(raw, open(f'{WORK}/raw.json', 'w'))
    subprocess.run([py, f'{sc}/score.py', f'{WORK}/raw.json', f'{WORK}/empty.json', f'{WORK}/out', '-', f'{WORK}/lock.json'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([py, f'{sc}/merge_compact.py', f'{WORK}/out', f'{WORK}/compact.csv', f'{WORK}/members.txt'], check=True, stdout=subprocess.DEVNULL)
    scores = json.load(open(f'{WORK}/out/scores.json'))
    price_of = {r['symbol']: r['price'] for r in scores if r.get('price') is not None}

    # track record
    log = state.get('pickLog', [])
    for n, s in enumerate(new_lock['picks'], 1):
        if not any(e['symbol'] == s and e['month'] == new_lock['month'] and not e.get('closedOn') for e in log):
            log.append({'month': new_lock['month'], 'pickedOn': today, 'symbol': s, 'pick': n, 'entryPrice': price_of.get(s) or out[s]['price'],
                        'benchmark': BENCH, 'benchEntry': spy_close})
    for e in log:
        if not e.get('closedOn') and e['symbol'] not in new_lock['picks']:
            e.update(closedOn=today, lastPrice=price_of.get(e['symbol']) or (out.get(e['symbol']) or {}).get('price'), benchLast=spy_close)
    track = []
    for e in log:
        last = e['lastPrice'] if e.get('closedOn') else (price_of.get(e['symbol']) or (out.get(e['symbol']) or {}).get('price'))
        bl = e['benchLast'] if e.get('closedOn') else spy_close
        r_, b_ = 100 * (last / e['entryPrice'] - 1), 100 * (bl / e['benchEntry'] - 1)
        track.append({'month': e['month'], 'pickedOn': e['pickedOn'], 'symbol': e['symbol'], 'pick': e['pick'], 'entryPrice': e['entryPrice'],
                      'benchmark': e['benchmark'], 'benchEntry': e['benchEntry'], 'lastPrice': round(last, 2), 'returnPct': round(r_, 2),
                      'benchReturnPct': round(b_, 2), 'excessPct': round(r_ - b_, 2), 'asOf': today, 'status': 'Closed' if e.get('closedOn') else 'Open'})

    # backtest
    say('backtest')
    try:
        bt, bts = backtest(adj, sorted(adj[BENCH]))
    except Exception as e:
        bt = bts = None; errs.append(f'backtest: {e}')

    json.dump(scores, open(f'{LIVE}/scores.json', 'w'), separators=(',', ':'))
    json.dump(json.load(open(f'{WORK}/out/prices.json')), open(f'{LIVE}/prices.json', 'w'))
    json.dump(track, open(f'{LIVE}/track.json', 'w'), indent=1)
    if bt:
        json.dump(bt, open(f'{LIVE}/backtest.json', 'w'), separators=(',', ':'))
        json.dump(bts, open(f'{LIVE}/backtest_summary.json', 'w'))
    state = {'asOf': today, 'universe': 'S&P 500', 'benchmark': BENCH, 'checks': ['200-DMA', 'Earnings', 'RSI', 'Momentum', 'P/E', 'PEG', 'Sharpe'],
             'lock': {k: new_lock[k] for k in ('month', 'picks', 'lockedOn')}, 'replaced': new_lock.get('replaced', []), 'pickLog': log, 'shortlist': short}
    json.dump(state, open(state_path, 'w'), indent=1)
    run = {'asOf': today, 'finishedAt': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'members': len(mem), 'scored': len(compact),
           'passedSix': len(full), 'shortlist': short, 'picks': new_lock['picks'], 'replaced': new_lock.get('replaced', []),
           'spyClose': spy_close, 'backtest': bool(bt), 'errors': errs[:50]}
    json.dump(run, open(f'{LIVE}/run.json', 'w'), indent=1)
    print(json.dumps(run, indent=1))


if __name__ == '__main__':
    main()
