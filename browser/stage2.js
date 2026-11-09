// STAGE 2 — earnings date and analyst data for the shortlist. Run in a finance.yahoo.com tab. Set SL to the shortlisted symbols.
// Returns {errs, res}; save res as outlook.json ({SYMBOL: {targetMean, recMean, analysts, fwdPE, epsNY, epsNY90, revUp30, revDown30, nextEarnings}}).
const SL = ['AAPL'];
const get = async (u) => (await fetch(u, {credentials: 'include'})).json();
const crumb = await (await fetch('https://query1.finance.yahoo.com/v1/test/getcrumb', {credentials: 'include'})).text();
const res = {}, errs = [];
for (const s of SL) {
  const o = {};
  try {
    const Q = (await get(`https://query2.finance.yahoo.com/v10/finance/quoteSummary/${s}?modules=financialData,earningsTrend,defaultKeyStatistics,calendarEvents&crumb=${encodeURIComponent(crumb)}`)).quoteSummary.result[0];
    const rw = (x) => x && x.raw != null ? x.raw : null, f = Q.financialData, ny = (Q.earningsTrend.trend || []).find((t) => t.period === '+1y') || {};
    o.outlook = {targetMean: rw(f.targetMeanPrice), recMean: rw(f.recommendationMean), analysts: rw(f.numberOfAnalystOpinions), fwdPE: rw(Q.defaultKeyStatistics.forwardPE),
      epsNY: rw(ny.epsTrend && ny.epsTrend.current), epsNY90: rw(ny.epsTrend && ny.epsTrend['90daysAgo']), revUp30: rw(ny.epsRevisions && ny.epsRevisions.upLast30days) ?? 0,
      revDown30: rw(ny.epsRevisions && ny.epsRevisions.downLast30days) ?? 0, nextEarnings: ((Q.calendarEvents.earnings || {}).earningsDate || []).map((d) => d.fmt)[0] || null};
  } catch (e) { errs.push(s + ' outlook ' + e.message); }
  res[s] = o.outlook;
}
window.__stage2 = res; JSON.stringify({errs, res})
