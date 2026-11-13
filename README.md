# S&P 500 Top 3 Agent

An AI agent that runs a personal stock checklist over every S&P 500 stock, picks the top 3 to research each month, explains why, and tracks how those picks do against SPY on a live dashboard.

It replaces a manual routine: opening each stock on a watchlist, checking the same numbers one by one, and deciding on a shortlist. See [docs/overview.md](docs/overview.md) for the one-page overview.

> A ranking for deciding what to research next, not investment advice.

## Runs on its own

- **Every US trading day, with no laptop.** A GitHub Actions job in this repo (`.github/workflows/daily.yml`) runs at 9:00 AM IST, Tuesday to Saturday, after each US trading day. It pulls S&P 500 membership from Wikipedia and prices, valuations and analyst data from Yahoo Finance, scores every stock, re-runs the backtest and saves the results to `data/live/`.
- **Claude reasons, checks itself and publishes.** A scheduled Claude task in the cloud picks up `data/live/` at 10:17 AM IST (retrying at 1:17 PM). It decides whether the data is fresh and complete enough to publish, writes the notes and bull and bear cases, and reads each pick's recent headlines (`news.json`) to judge news sentiment. Before publishing it grades its own writing on four evals (correctness, no hallucinations, relevance, coherence), rewrites anything that fails, and emails a summary with the eval results. The rules choose the picks; Claude never does.
- **Corrects its own picks.** Each run re-checks the 3 picks and swaps one out if it falls below its 200-DMA or fails the P/E check. A fresh top 3 is chosen at the start of every month. The lock and the pick log live in `data/live/state.json`.
- **No manual steps on a normal day.** You only step in to change the checklist, the universe or the schedule. If a run can't get the data, it publishes nothing that day rather than partial data.

The public dashboard link is a frozen snapshot of the first run (Nov 9, 2026). Claude can only update a dashboard that isn't public, so the daily runs publish to a private one.

## The seven checks

| Check | Pass rule |
| --- | --- |
| 200-DMA | Price above its 200-day average |
| Earnings | No report in the next 14 days |
| RSI (14-day) | 30 to 65, or below 30 and rising |
| Momentum | 3-month return above 0, or 12-month trend up with price above the 20-day average |
| P/E | Forward P/E above 0 and at most 40 |
| PEG | Forward P/E ÷ expected EPS growth (%) at most 2.0 |
| Sharpe | 1-year Sharpe of at least 1.0 (4% risk-free rate) |

**Score (0–100):** 30% trend, 30% momentum, 15% entry timing, 15% valuation, 10% analyst outlook. Trend, momentum and entry are scaled by each stock's volatility.

**Picks:** the 3 highest scores among stocks that pass all seven checks. They are locked for the calendar month and replaced early only if a pick falls below its 200-DMA or fails the P/E check.

## How a run works

```
Wikipedia S&P 500 list ──► members.js ──► members.txt
                                              │
Yahoo Finance (prices, P/E, EPS) ──► screen.js ──► full.csv (passed 6 checks) + compact.csv (all ~500)
                                              │
top 15 + locked picks ──► stage2.js ──► outlook.json (earnings date, analyst data)
                                              │
build_raw.py ──► raw.json ──► score.py ──► scores.json, prices.json, lock.json
                                              │
merge_compact.py ──► adds every screened-out stock with the check it failed
                                              │
dashboard/index.html ◄── scores, prices, track, backtest
```

Daily runs use `collector/run_daily.py`, the Python version of the browser scripts with the same rules, on GitHub Actions. The browser scripts are kept for running a screen by hand: paste them into your browser's developer console on a `finance.yahoo.com` (or Wikipedia) tab.

## Repo layout

| Path | What it is |
| --- | --- |
| `browser/members.js` | Pulls S&P 500 membership from Wikipedia in Yahoo symbol format |
| `browser/screen.js` | Stage 1: prices, technicals, Sharpe and valuation for every member, the six non-earnings checks, and a stage-1 score |
| `browser/stage2.js` | Stage 2: earnings date, analyst target, ratings and EPS revisions for the shortlist |
| `browser/backtest.js` | Monthly backtest of the price checks on today's members, against SPY |
| `collector/run_daily.py` | The whole daily run without a browser: membership, prices, valuation, analyst data, scoring, track record and backtest |
| `.github/workflows/daily.yml` | Runs the collector on GitHub's servers every weekday morning and commits `data/live/` |
| `data/live/` | The latest daily results and the saved state (lock and pick log) |
| `scoring/build_raw.py` | Combines stage 1 and stage 2 output into `raw.json` |
| `scoring/score.py` | Runs all seven checks, scores and ranks, sets signals, applies the monthly lock, writes the dashboard datasets |
| `scoring/merge_compact.py` | Adds the screened-out stocks, with the reason each one failed |
| `dashboard/index.html` | The dashboard page (runs inside a Claude Data artifact) |
| `dashboard/preview.html` | A standalone preview of the dashboard using the sample data |
| `agent/refresh_prompt.md` | The earlier laptop-based refresh instructions, kept for reference |
| `data/sample/` | A full run from Nov 9, 2026 (inputs and outputs) |
| `docs/overview.md` | One-page overview: why, what and how |

## Run the scoring on the sample data

Python 3.9+ with the standard library only.

```bash
mkdir -p run && cd run
echo '[]' > empty.json
python3 ../scoring/build_raw.py ../data/sample/sp500_members.txt ../data/sample/full.csv ../data/sample/outlook.json raw.json 2026-11-09T17:35:00Z
python3 ../scoring/score.py raw.json empty.json out ../data/sample/notes.json
python3 ../scoring/merge_compact.py out ../data/sample/compact.csv ../data/sample/sp500_members.txt
cat out/lock.json   # {"month": "2026-11", "picks": ["BIIB", "HUM", "MET"], ...}
```

## Preview the dashboard

```bash
python3 -m http.server 8000
# open http://localhost:8000/dashboard/preview.html
```

`index.html` is written for Claude's dashboard runtime (`dash.data`, `dash.draw`). `preview.html` stands in for that runtime and loads `data/sample/`.

## Data sources

- **Membership:** [Wikipedia's list of S&P 500 companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)
- **Prices, forward P/E, EPS estimates, analyst data, earnings dates:** Yahoo Finance (unofficial endpoints, which can change or rate-limit without notice)
- **Price cross-check:** Alpha Vantage `GLOBAL_QUOTE` (free tier)

## Backtest, read with caution

Monthly from Nov 2023, testing the price checks only (historical P/E, PEG, earnings dates and analyst data weren't available):

| Variant | 3-year return | Worst fall |
| --- | --- | --- |
| Top 3, held a month (used now) | +163% | −32% |
| Same, rebalanced weekly | +255% | −38% |
| Top 10, monthly | +72% | −43% |
| Equal-weight all current members | +98% | −18% |
| SPY buy and hold | +85% | −19% |

It tests **today's** members, and several of the strategy's picks (AppLovin, Palantir, Dell, Super Micro, Coinbase, Robinhood) joined the index only after big gains, so the strategy's lead is overstated. The live track record against SPY, which started Nov 9, 2026, is the real test.

## History

1. Started as a 10-symbol TradingView watchlist (stocks, gold, crypto).
2. Moved to the Nasdaq-100 for a bigger universe.
3. Added P/E, PEG and Sharpe; dropped news sentiment from the score. (News came back in Nov 2026 as context for the agent's analysis, not as a scoring input.)
4. Moved to the S&P 500, because the AI-heavy Nasdaq-100 made PEG and Sharpe comparisons unfair; the benchmark switched from QQQ to SPY.
