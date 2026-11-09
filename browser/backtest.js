// BACKTEST — run in a finance.yahoo.com tab (same-origin fetches to Yahoo's chart API).
// Tests the price-only part of the checklist (200-DMA, RSI, momentum + signal) on today's index members,
// monthly from Nov 2023, and compares variants. Historical P/E, PEG, earnings dates and analyst data
// are not available, so those checks are not in the test. Using today's members overstates returns.
// Set SYMS to the comma-separated member list (Yahoo format) and BENCH to the benchmark ETF.
const SYMS = 'AAPL,MSFT';
const BENCH = 'SPY', START = '2023-11-01';
const syms = SYMS.split(',');
const H = {};
const one = async (s) => { try {
  const j = await (await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${s}?range=5y&interval=1d&events=div,split`)).json();
  const r = j.chart.result[0]; const ac = (r.indicators.adjclose && r.indicators.adjclose[0].adjclose) || r.indicators.quote[0].close;
  const m = new Map(); r.timestamp.forEach((t, i) => { if (ac[i] != null) m.set(new Date(t * 1000).toISOString().slice(0, 10), ac[i]); });
  H[s] = m; } catch (e) { /* skipped */ } };
const all = syms.concat([BENCH]);
for (let i = 0; i < all.length; i += 20) await Promise.all(all.slice(i, i + 20).map(one));
const D = [...H[BENCH].keys()].sort(); const S = syms.filter((s) => H[s]);
const C = {}; for (const s of [...S, BENCH]) { let last = null; C[s] = D.map((d) => { const v = H[s].get(d); if (v != null) last = v; return last; }); }
const clip = (x) => Math.max(0, Math.min(100, x));
const sma = (a, i, n) => { if (i < n - 1 || a[i - n + 1] == null) return null; let t = 0; for (let k = i - n + 1; k <= i; k++) t += a[k]; return t / n; };
const RSI = {}; for (const s of S) { const a = C[s], r = new Array(D.length).fill(null); let g = 0, l = 0; const st = a.findIndex((v) => v != null);
  if (st >= 0) for (let i = st + 1; i < a.length; i++) { const ch = a[i] - a[i - 1], up = Math.max(ch, 0), dn = Math.max(-ch, 0);
    if (i - st <= 14) { g += up / 14; l += dn / 14; if (i - st === 14) r[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); }
    else { g = (g * 13 + up) / 14; l = (l * 13 + dn) / 14; r[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); } } RSI[s] = r; }
// Same price rules and score weights as score.py, without valuation and analyst outlook: (0.30 trend + 0.30 mom + 0.15 entry) / 0.75
const evalAt = (s, i) => { const a = C[s]; if (i < 260 || a[i - 252] == null) return null; const p = a[i];
  const s20 = sma(a, i, 20), s50 = sma(a, i, 50), s200 = sma(a, i, 200); if (!s200) return null;
  const rsi = RSI[s][i], rsi5 = RSI[s][i - 5] ?? rsi; let hi = 0; for (let k = i - 251; k <= i; k++) hi = Math.max(hi, a[k]);
  const r3m = p / a[i - 63] - 1, m121 = a[i - 21] / a[i - 252] - 1; const lr = []; for (let k = i - 59; k <= i; k++) lr.push(Math.log(a[k] / a[k - 1]));
  const mu = lr.reduce((x, y) => x + y) / 60, vol = Math.sqrt(lr.reduce((x, y) => x + (y - mu) ** 2, 0) / 59) * Math.sqrt(252);
  const k = vol ? Math.max(0.5, Math.min(1.5, 0.25 / vol)) : 1; const vs50 = p / s50 - 1, vs200 = p / s200 - 1, off = p / hi - 1;
  const trend = clip(50 + 250 * vs200 * k), mom = 0.5 * clip(50 + 166.7 * r3m * k) + 0.5 * clip(50 + 125 * m121 * k);
  const entry = 0.5 * clip((70 - rsi) / 40 * 100) + 0.5 * clip(30 + 280 * -off * k);
  const score = (0.30 * trend + 0.30 * mom + 0.15 * entry) / 0.75; const turning = rsi > rsi5;
  let sig; if (rsi > 70) sig = 'S'; else if ((rsi < 40 || off <= -0.15) && vs200 > 0) sig = turning ? 'D' : 'F';
  else if (vs50 > 0 && vs200 > 0 && rsi >= 45 && rsi <= 70) sig = 'T'; else if (vs200 < -0.03 && r3m < 0) sig = 'A'; else sig = 'W';
  const ok = vs200 > 0 && ((rsi >= 30 && rsi <= 65) || (rsi < 30 && turning)) && (r3m > 0 || (m121 > 0 && p > s20)) && 'DTW'.includes(sig);
  return {score, ok}; };
const start = D.findIndex((d) => d >= START);
const monthIdx = D.map((d, i) => i).filter((i) => i >= start && (i === start || D[i].slice(0, 7) !== D[i - 1].slice(0, 7)));
const weekIdx = []; for (let i = start; i < D.length; i += 5) weekIdx.push(i);
const run = (rebal, pickFn) => { const rs = new Set(rebal); let hold = [], eq = 1, peak = 1, dd = 0; const curve = [{i: start, v: 1, picks: ''}];
  for (let i = start; i < D.length; i++) { if (i > start) { const rets = hold.map((s) => C[s][i] / C[s][i - 1] - 1).filter((x) => isFinite(x)); const r = rets.length ? rets.reduce((x, y) => x + y) / hold.length : 0; eq *= 1 + r; peak = Math.max(peak, eq); dd = Math.min(dd, eq / peak - 1); }
    if (rs.has(i)) { if (i > start) curve.push({i, v: eq, picks: hold.join(' ')}); hold = pickFn(i); } }
  curve.push({i: D.length - 1, v: eq, picks: hold.join(' ')}); return {eq, dd, curve}; };
const topN = (n) => (i) => S.map((s) => [s, evalAt(s, i)]).filter(([, e]) => e && e.ok).sort((a, b) => b[1].score - a[1].score).slice(0, n).map((x) => x[0]);
const allEW = (i) => S.filter((s) => C[s][i] != null && C[s][i - 1] != null);
const strat = run(monthIdx, topN(3)), wk = run(weekIdx, topN(3)), t10 = run(monthIdx, topN(10)), ew = run(monthIdx, allEW), bench = run(monthIdx, () => [BENCH]);
const at = (r, i) => r.curve.find((c) => c.i === i);
const curve = monthIdx.concat([D.length - 1]).map((i, j) => ({date: D[i], strategy: +(j ? at(strat, i).v : 1).toFixed(4), watchlist: +(j ? at(ew, i).v : 1).toFixed(4), spy: +(j ? at(bench, i).v : 1).toFixed(4), picks: j ? at(strat, i).picks : ''}));
const pct = (x) => Math.round(100 * x);
const summary = [['Top 3, all price checks, held a month (used now)', strat, true], ['Same, rebalanced weekly', wk, false], ['Top 10 instead of top 3, monthly', t10, false], ['Equal-weight all current members', ew, false], [`${BENCH} buy and hold`, bench, false]]
  .map(([variant, r, current]) => ({variant, total: pct(r.eq - 1), maxDD: pct(r.dd), current}));
window.__backtest = {curve, summary};
JSON.stringify(summary)
// Then read JSON.stringify(window.__backtest.curve) in a separate call and save it as backtest.json; save summary as backtest_summary.json.
