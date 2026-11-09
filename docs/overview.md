# S&P 500 Top 3 Agent: One-Page Overview

## Why it exists

Picking what to research next meant opening every stock on a watchlist, checking the same handful of numbers one by one, and then deciding on a shortlist. That takes hours, gets done inconsistently, and only covers the few names already on the list.

The agent automates that routine. It runs the same personal checklist (200-DMA, earnings date, RSI, momentum, P/E, PEG and Sharpe ratio) across all ~500 S&P 500 stocks and returns the 3 that best fit it, with the reasoning shown. The universe moved from the Nasdaq-100 to the S&P 500 because the Nasdaq-100 is dominated by AI stocks, where PEG and Sharpe don't compare fairly right now.

## What the agent does

It runs on its own every US trading day (6:47 AM IST, after the US close) and needs no manual steps on a normal day; it only needs the computer that runs the schedule switched on with the Claude desktop app open. On each run, Claude:

- Pulls the current S&P 500 membership and a year of prices, forward P/E and EPS estimates from Yahoo Finance, then cross-checks the picks' closing prices against Alpha Vantage.
- Runs the checks, scores every stock and ranks them.
- Pulls earnings dates and analyst data (target price, EPS revisions, ratings) for the 15-stock shortlist only.
- Writes a short note on each shortlisted stock, plus a bull case, bear case and catalysts for each pick, using only the numbers it pulled.
- Logs every pick's entry price and tracks its return against SPY.
- Publishes it all to a live dashboard showing the top 3, the shortlist, all ~500 stocks with the reason each one failed, the track record and a backtest.

## How it picks the top 3

A pick has to pass all seven checks, and then the highest scores win. In the first S&P 500 run (Nov 9, 2026), 499 stocks were screened, 50 passed the first six checks, 15 were shortlisted and 3 were picked: Biogen, Humana and MetLife.

| Check | Pass rule |
| --- | --- |
| 200-DMA | Price above its 200-day average |
| Earnings | No report in the next 14 days |
| RSI (14-day) | 30 to 65, or below 30 and rising |
| Momentum | 3-month return above 0, or 12-month trend up with price above the 20-day average |
| P/E | Forward P/E above 0 and at most 40 |
| PEG | At most 2.0 |
| Sharpe | 1-year Sharpe of at least 0.5 |

1. **Screen:** six checks (all except earnings) run on every stock. Stocks that are overbought or still falling are dropped too.
2. **Shortlist:** the 15 highest scorers get the earnings check and the analyst data.
3. **Score (0 to 100):** 30% trend, 30% momentum, 15% entry timing (RSI and distance from the 52-week high), 15% valuation (P/E and PEG), 10% analyst outlook. Each score is adjusted for the stock's volatility, so a calm stock's move counts for more.
4. **Lock and self-correct:** the top 3 are locked for the month. Every daily run re-checks them and swaps a pick out automatically if it drops below its 200-DMA or fails the P/E check. A fresh top 3 is chosen at the start of each month.

## Why it beats a standard screener

A standard screener filters and stops: you get a long list that passes your thresholds, and the judgement is still up to you. This agent goes further in five ways.

- **It ranks and decides.** It doesn't stop at 50 passing stocks. It scores them and names 3, and shows exactly why each one ranked where it did.
- **It weighs timing and risk, not just whether a stock passes.** RSI rising or falling, distance from the 52-week high, volatility and Sharpe all feed the score, so a strong but overstretched stock ranks below a steadier one.
- **It explains in plain words.** Each pick comes with a note, a bull case, a bear case and catalysts. Every screened-out stock shows the check it failed.
- **It holds and tracks.** Picks are locked for a month rather than reshuffled daily, and every pick is measured against SPY.
- **It tests itself.** A backtest and a live track record show whether the rules actually work, which a screener never tells you.

## Limits

The agent ranks stocks to decide what to research next; it does not give investment advice. Its backtest covers only the price checks, and it uses today's index members, which overstates returns: the strategy made +163% over three years against +85% for SPY, but its worst fall was −32% against SPY's −19%. The live track record against SPY, which started Nov 9, 2026, is the real test.
