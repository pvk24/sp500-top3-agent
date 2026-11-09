# Daily refresh instructions for Claude

These are the instructions a scheduled Claude run follows to refresh the dashboard. They assume:

- Claude has a browser it can run JavaScript in (the scripts call Yahoo Finance from a `finance.yahoo.com` tab, which a plain server can't reach the same way).
- The dashboard is a Claude Data artifact with datasets `scores`, `prices`, `track`, `backtest` and `backtestSummary`, plus a state document `state/lastSignals`.
- The scripts in `browser/` and `scoring/` are available to the run.

Replace `<DASHBOARD_ID>` with your artifact's id.

---

Refresh the "S&P 500 Top 3 Opportunities" dashboard (`<DASHBOARD_ID>`). Work unattended and don't ask questions. This is a ranking for deciding what to research, not investment advice. Make as few artifact writes as possible.

1. **Browser.** If the browser can't be reached, stop and report that the refresh was skipped. Never publish partial data.
2. **Membership.** Open https://en.wikipedia.org/wiki/List_of_S%26P_500_companies, run `browser/members.js` and save the result as `members.txt`. If fewer than 490 members come back, stop and report it.
3. **Stage 1.** Open https://finance.yahoo.com/quote/MSFT/ and run `browser/screen.js` with `SYMS` set to the member symbols.
   - Save its `full` output as `full.csv`.
   - Read `window.__compact.join('\n')` and save it as `compact.csv`, with the header `s,score,rsi,vs200,r3m,pe,peg,sharpe,checks,sig`.
   - If this month's locked picks aren't in `full.csv`, add their rows from `window.__u` so they get re-checked.
4. **Shortlist.** Take the 15 highest stage-1 scores in `compact.csv` among the `full.csv` stocks, plus this month's locked picks.
5. **Stage 2.** Run `browser/stage2.js` with `SL` set to the shortlist and save `res` as `outlook.json`.
6. **Score.**
   - `python3 scoring/build_raw.py members.txt full.csv outlook.json raw.json`
   - Write the previous `state/lastSignals.lock` to `lock.json`, or `{}` if there is none.
   - `python3 scoring/score.py raw.json empty.json out - lock.json`
   - For each pick in `out/lock.json`, add `"spark"` to its `raw.json` item: the last 64 values of `window.__spark[symbol]`.
7. **Notes.** Write `notes.json`.
   - For each shortlisted stock, give a one- or two-sentence `note` with concrete numbers from `out/scores.json`: P/E, PEG, Sharpe, RSI, distance from the 52-week high and the 200-DMA, analyst target and EPS revisions.
   - For each of the 3 picks, also give `bull`, `bear` and `catalyst`. Flag earnings within 14 days, stale analyst targets and high volatility.
   - Then run:
     - `python3 scoring/score.py raw.json empty.json out notes.json lock.json`
     - `python3 scoring/merge_compact.py out compact.csv members.txt`
8. **Track record.** Start from `state/lastSignals.pickLog`.
   - Log any new pick with `entryPrice` set to today's price and `benchEntry` set to today's SPY close.
   - Close any open entry that is no longer a pick.
   - Write `out/track.json`: one row per entry with `{month, pickedOn, symbol, pick, entryPrice, benchmark: "SPY", benchEntry, lastPrice, returnPct, benchReturnPct, excessPct, asOf, status}`.
9. **Cross-check (optional).** Call Alpha Vantage `GLOBAL_QUOTE` for each pick and note any previous-close gap over 1%.
10. **Publish.**
    - Upload `out/scores.json`, `out/prices.json` and `out/track.json`.
    - In one write, point `datasets/scores`, `datasets/prices` and `datasets/track` at the new files, and set `state/lastSignals` with `{asOf, universe: "S&P 500", benchmark: "SPY", checks, lock, pickLog, shortlist}`.
11. **Report.** If the picks changed or a pick isn't "On track", list the top 3 with score, signal, any failing check and return vs SPY. Otherwise reply in one line: "No change: <picks>, all on track; vs SPY <avg excess>%". Always mention errors, membership changes and price mismatches.
