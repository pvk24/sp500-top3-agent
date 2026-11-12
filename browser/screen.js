// STAGE 1 for a large universe (S&P 500). Run in the finance.yahoo.com tab.
// Replace SYMS with the comma-separated member list (Yahoo format: BRK-B, not BRK.B; GOOG only), and keep QQQ appended.
// It applies the six stage-1 checks and the screened-out score with the SAME rules as score.py, and returns:
//   compact: one short row per stock (enough for the "All stocks" table and the funnel)
//   full: complete raw rows for the stocks that pass all six checks with an OK signal (the shortlist candidates), plus QQQ
const SYMS = 'AAPL,MSFT';
const U = SYMS.split(',').concat(['QQQ']);
const R = (x, n = 4) => x == null || !isFinite(x) ? null : +(+x).toFixed(n);
const sma = (a, n) => a.length >= n ? a.slice(-n).reduce((x, y) => x + y, 0) / n : null;
const ret = (a, n) => a.length > n ? a.at(-1) / a.at(-1 - n) - 1 : null;
const clip = (x) => Math.max(0, Math.min(100, x));
function rsi(a, n = 14) { if (a.length < 20) return null; let g = 0, l = 0; for (let i = 1; i <= n; i++) { const d = a[i] - a[i - 1]; d > 0 ? g += d : l -= d; } g /= n; l /= n;
  for (let i = n + 1; i < a.length; i++) { const d = a[i] - a[i - 1]; g = (g * (n - 1) + Math.max(d, 0)) / n; l = (l * (n - 1) + Math.max(-d, 0)) / n; } return l === 0 ? 100 : 100 - 100 / (1 + g / l); }
const get = async (u) => (await fetch(u, {credentials: 'include'})).json();
const out = {}, spark = {}, errs = [];
for (let b = 0; b < U.length; b += 20) {
  await Promise.all(U.slice(b, b + 20).map(async (s) => {
    try {
      const r = (await get(`https://query1.finance.yahoo.com/v8/finance/chart/${s}?range=14mo&interval=1d`)).chart.result[0];
      const c = r.timestamp.map((t, i) => r.indicators.quote[0].close[i]).filter((x) => x != null), yr = c.slice(-252);
      const lr = c.slice(-61).map((x, i, a) => i ? Math.log(x / a[i - 1]) : 0).slice(1), mu = lr.reduce((a, b) => a + b, 0) / lr.length;
      out[s] = {s, price: R(r.meta.regularMarketPrice), prevClose: R(c.at(-2)), n: c.length,
        r1w: R(ret(c, 5)), r1m: R(ret(c, 21)), r3m: R(ret(c, 63)), r6m: R(ret(c, 126)), r12m: R(ret(c, 252)),
        mom12_1: R(c.length > 252 ? c.at(-22) / c.at(-253) - 1 : null), sma20: R(sma(c, 20)), sma50: R(sma(c, 50)), sma200: R(sma(c, 200)),
        rsi14: R(rsi(c.slice(-120)), 2), rsi14_5d: R(rsi(c.slice(-125, -5)), 2), hi52: R(Math.max(...yr)), lo52: R(Math.min(...yr)),
        vol60: R(Math.sqrt(lr.reduce((a, b) => a + (b - mu) ** 2, 0) / (lr.length - 1)) * Math.sqrt(252)),
        sharpe1y: (() => { if (c.length < 253) return null; const d = c.slice(-253).map((x, i, a) => i ? x / a[i - 1] - 1 : 0).slice(1), m = d.reduce((a, b) => a + b, 0) / d.length;
          const sd = Math.sqrt(d.reduce((a, b) => a + (b - m) ** 2, 0) / (d.length - 1)); return R((m * 252 - 0.04) / (sd * Math.sqrt(252)), 3); })()};
      const step = Math.max(1, Math.floor(yr.length / 52)); spark[s] = yr.filter((_, i) => i % step === 0).concat([c.at(-1)]).map((x) => R(x, 2));
    } catch (e) { errs.push(s + ': ' + e.message); }
  }));
}
const crumb = await (await fetch('https://query1.finance.yahoo.com/v1/test/getcrumb', {credentials: 'include'})).text();
const syms = Object.keys(out).filter((s) => s !== 'QQQ');
for (let i = 0; i < syms.length; i += 50) {
  try { const j = await get(`https://query2.finance.yahoo.com/v7/finance/quote?symbols=${syms.slice(i, i + 50).join(',')}&fields=forwardPE,epsForward,epsCurrentYear,epsTrailingTwelveMonths&crumb=${encodeURIComponent(crumb)}`);
    for (const q of j.quoteResponse.result) if (out[q.symbol]) Object.assign(out[q.symbol], {fwdPE: R(q.forwardPE), epsFwd: R(q.epsForward), epsCY: R(q.epsCurrentYear), epsTTM: R(q.epsTrailingTwelveMonths)}); }
  catch (e) { errs.push('valuation: ' + e.message); }
}
// Same rules as score.py (screened-out path: no analyst outlook, no earnings check)
const PE_MAX = 40, PEG_MAX = 2.0, SHARPE_MIN = 1.0, compact = [], full = [], skipped = [];
for (const s of syms) {
  const it = out[s];
  if (!it.sma200 || !it.hi52 || it.mom12_1 == null) { skipped.push(s); continue; }
  const p = it.price, rsiv = it.rsi14, rsi5 = it.rsi14_5d ?? rsiv, vs50 = p / it.sma50 - 1, vs200 = p / it.sma200 - 1, vs20 = it.sma20 ? p / it.sma20 - 1 : 0, off = p / it.hi52 - 1;
  const r3m = it.r3m || 0, m121 = it.mom12_1 || 0, k = it.vol60 ? Math.max(0.5, Math.min(1.5, 0.25 / it.vol60)) : 1;
  const trend = clip(50 + 250 * vs200 * k), mom = 0.5 * clip(50 + 166.7 * r3m * k) + 0.5 * clip(50 + 125 * m121 * k);
  const entry = 0.5 * clip((70 - rsiv) / 40 * 100) + 0.5 * clip(30 + 280 * -off * k);
  const pe = it.fwdPE, ef = it.epsFwd, ec = it.epsCY, et = it.epsTTM, base = ec && ec > 0 ? ec : (et && et > 0 ? et : null);
  const growth = ef && base ? ef / base - 1 : null, peg = pe && pe > 0 && growth && growth > 0 ? pe / (100 * growth) : null;
  const val = 0.5 * (pe && pe > 0 ? clip((PE_MAX - pe) / 30 * 100) : 0) + 0.5 * (peg != null ? clip((2.5 - peg) / 2 * 100) : 0);
  const score = (0.30 * trend + 0.30 * mom + 0.15 * entry + 0.15 * val) / 0.90;
  const turning = p > (it.sma20 ?? p) || rsiv > rsi5 + 3, pull = rsiv < 40 || off <= -0.15;
  const sig = rsiv > 70 ? 'S' : pull && vs200 > 0 ? (turning ? 'D' : 'F') : vs50 > 0 && vs200 > 0 && rsiv >= 45 && rsiv <= 70 ? 'T' : vs200 < -0.03 && r3m < 0 ? 'A' : 'W';
  const ck = [vs200 > 0, (rsiv >= 30 && rsiv <= 65) || (rsiv < 30 && rsiv > rsi5), r3m > 0 || (m121 > 0 && vs20 > 0), pe != null && pe > 0 && pe <= PE_MAX, peg != null && peg <= PEG_MAX, it.sharpe1y != null && it.sharpe1y >= SHARPE_MIN];
  compact.push([s, score.toFixed(1), rsiv.toFixed(1), (100 * vs200).toFixed(1), (100 * r3m).toFixed(1), pe == null ? '' : pe.toFixed(1), peg == null ? '' : peg.toFixed(2), it.sharpe1y == null ? '' : it.sharpe1y.toFixed(2), ck.map(Number).join(''), sig].join(','));
  if (ck.every(Boolean) && 'DTW'.includes(sig)) full.push(s);
}
window.__u = out; window.__spark = spark; window.__compact = compact; window.__fullSyms = full;
const cols = ['s','price','prevClose','n','r1w','r1m','r3m','r6m','r12m','mom12_1','sma20','sma50','sma200','rsi14','rsi14_5d','hi52','lo52','vol60','sharpe1y','fwdPE','epsFwd','epsCY','epsTTM'];
({errs, skipped, counts: {universe: syms.length, scored: compact.length, passingSix: full.length},
  full: cols.join(',') + '\n' + full.concat(['QQQ']).map((s) => cols.map((c) => out[s][c] ?? '').join(',')).join('\n')})
// Then read window.__compact.join('\n') in a separate call (s,score,rsi,vs200%,r3m%,pe,peg,sharpe,checks[200,rsi,mom,pe,peg,sharpe],signal S/D/F/T/A/W).
