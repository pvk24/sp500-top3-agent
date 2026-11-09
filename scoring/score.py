"""Score S&P 500 stocks against a seven-point checklist: 200-DMA, earnings, RSI, momentum, P/E, PEG, Sharpe ratio.

Usage: python3 score.py raw.json headlines.json outdir [notes.json | -] [lock.json]
  headlines.json  unused since news was dropped; pass a file containing []
  notes.json      {SYMBOL: {"note": "...", "bull": "...", "bear": "...", "catalyst": "..."}}, or - for auto notes
  lock.json       {"month": "YYYY-MM", "picks": [..], "lockedOn": "YYYY-MM-DD"} from the previous run

Picks are locked for the calendar month. A new lock is written to outdir/lock.json when the month changes,
the lock is missing, or a locked pick falls below its 200-DMA or fails the P/E check.
Writes outdir/scores.json, outdir/prices.json and outdir/lock.json.
"""
import json, sys, math, datetime as dt

raw = json.load(open(sys.argv[1])); heads = json.load(open(sys.argv[2])); out = sys.argv[3]
import os; os.makedirs(out, exist_ok=True)
notes = json.load(open(sys.argv[4])) if len(sys.argv) > 4 and sys.argv[4] != "-" else {}
lock = json.load(open(sys.argv[5])) if len(sys.argv) > 5 else {}
asof = dt.date.fromisoformat(raw["asof"][:10])
clip = lambda x: max(0.0, min(100.0, x))
r1 = lambda x, n=1: None if x is None else round(x, n)
pct = lambda x, n=1: None if x is None else round(100 * x, n)
EARNINGS_DAYS = 14  # no new pick inside this window before an earnings report
PE_MAX = 40         # forward P/E must be positive and at most this
PEG_MAX = 2.0       # forward P/E / next-year EPS growth (%) must be at most this
SHARPE_MIN = 0.5    # 1-year Sharpe ratio (excess return over a 4% risk-free rate / volatility) must be at least this

rows, prices = [], []
skipped = []
for it in raw["items"]:
    if not it.get("sma200") or not it.get("hi52") or it.get("mom12_1") is None:
        skipped.append(it["s"]); continue          # under ~1 year of history: can't run the checks
    deep = it.get("stage", "Shortlist") == "Shortlist"   # news/earnings/analyst data only for the shortlist
    p = it["price"]; rsi = it["rsi14"]; rsi5 = it.get("rsi14_5d") or rsi
    vs50, vs200 = p / it["sma50"] - 1, p / it["sma200"] - 1
    vs20 = p / it["sma20"] - 1 if it.get("sma20") else 0
    off_high = p / it["hi52"] - 1
    r3m, m121 = it["r3m"] or 0, it["mom12_1"] or 0
    # Volatility scaling: a 10% move in a 25%-vol stock counts more than in a 50%-vol coin
    k = max(0.5, min(1.5, 0.25 / it["vol60"])) if it.get("vol60") else 1.0

    trend = clip(50 + 250 * vs200 * k)                                   # 200-DMA
    mom = 0.5 * clip(50 + 166.7 * r3m * k) + 0.5 * clip(50 + 125 * m121 * k)  # 3m and 12-1m
    rsi_pts = clip((70 - rsi) / 40 * 100)                                # RSI 30 -> 100, 70 -> 0
    high_pts = clip(30 + 280 * -off_high * k)                            # discount to 52w high
    entry = 0.5 * rsi_pts + 0.5 * high_pts

    # Valuation: forward P/E and PEG (forward P/E / expected EPS growth to next year, in %)
    pe = it.get("fwdPE"); ef, ec, et = it.get("epsFwd"), it.get("epsCY"), it.get("epsTTM")
    base = ec if ec and ec > 0 else (et if et and et > 0 else None)
    growth = ef / base - 1 if ef and base else None
    peg = pe / (100 * growth) if pe and pe > 0 and growth and growth > 0 else None
    val = (0.5 * (clip((PE_MAX - pe) / 30 * 100) if pe and pe > 0 else 0)
           + 0.5 * (clip((2.5 - peg) / 2 * 100) if peg is not None else 0))   # P/E 10 -> 100, 40 -> 0; PEG 0.5 -> 100, 2.5 -> 0

    o = it.get("outlook"); outl = upside = eps_rev = None; stale = False; days_to_earn = None
    if o and o.get("nextEarnings"):
        days_to_earn = (dt.date.fromisoformat(o["nextEarnings"]) - asof).days
        if days_to_earn < 0: days_to_earn = None
    if o and o.get("targetMean") and o.get("epsNY") and o.get("epsNY90") and o.get("recMean"):
        upside = o["targetMean"] / p - 1
        stale = upside > 0.40 and (it["r1m"] or 0) < -0.15       # price fell faster than targets were cut
        up_eff = min(upside, 0.15 if stale else 0.30)
        eps_rev = o["epsNY"] / o["epsNY90"] - 1
        tot = (o["revUp30"] or 0) + (o["revDown30"] or 0)
        breadth = ((o["revUp30"] or 0) - (o["revDown30"] or 0)) / tot if tot else 0
        outl = (0.35 * clip(50 + 166.7 * up_eff) + 0.30 * clip(50 + 500 * eps_rev)
                + 0.15 * clip(50 + 50 * breadth) + 0.20 * clip((3 - o["recMean"]) / 2 * 100))
        score = 0.30 * trend + 0.30 * mom + 0.15 * entry + 0.15 * val + 0.10 * outl
    else:
        o = None if not (o and o.get("nextEarnings")) else o
        score = (0.30 * trend + 0.30 * mom + 0.15 * entry + 0.15 * val) / 0.90

    turning = p > it.get("sma20", p) or rsi > rsi5 + 3                  # bounce has started
    earn_soon = days_to_earn is not None and days_to_earn <= EARNINGS_DAYS
    checks = {
        "chk200": vs200 > 0,
        "chkEarnings": (not earn_soon) if deep else None,
        "chkRsi": (30 <= rsi <= 65) or (rsi < 30 and rsi > rsi5),
        "chkMomentum": r3m > 0 or (m121 > 0 and vs20 > 0),
        "chkPE": pe is not None and 0 < pe <= PE_MAX,
        "chkPEG": peg is not None and peg <= PEG_MAX,
        "chkSharpe": it.get("sharpe1y") is not None and it["sharpe1y"] >= SHARPE_MIN,
    }
    passed = sum(1 for v in checks.values() if v)

    pull = rsi < 40 or off_high <= -0.15
    if rsi > 70:
        sig = "Wait: stretched"
    elif earn_soon:
        sig = "Wait: earnings soon"
    elif pull and (vs200 > 0 or (outl or 0) >= 65):
        sig = "Buy the dip" if turning else "Wait: still falling"
    elif vs50 > 0 and vs200 > 0 and 45 <= rsi <= 70:
        sig = "Trend buy"
    elif vs200 < -0.03 and r3m < 0:
        sig = "Avoid: downtrend"
    else:
        sig = "Watch"

    n = notes.get(it["s"], {})
    if isinstance(n, str): n = {"note": n}
    if not n.get("note"):
        why = []
        if not checks["chk200"]: why.append(f"{abs(100 * vs200):.0f}% below its 200-DMA")
        if not checks["chkRsi"]: why.append(f"RSI {rsi:.0f} " + ("overbought" if rsi > 65 else "and still falling"))
        if not checks["chkMomentum"]: why.append(f"3-month return {100 * r3m:+.0f}%")
        if not checks["chkPE"]: why.append("no forward P/E (loss-making)" if not pe or pe <= 0 else f"forward P/E {pe:.0f} above {PE_MAX}")
        if not checks["chkPEG"] and pe and pe > 0: why.append("PEG can't be computed (no positive EPS growth)" if peg is None else f"PEG {peg:.1f} above {PEG_MAX}")
        if not checks["chkSharpe"]: why.append(f"1-year Sharpe {it['sharpe1y']:.2f} below {SHARPE_MIN}" if it.get("sharpe1y") is not None else "no 1-year Sharpe ratio")
        if checks["chkEarnings"] is False: why.append(f"earnings in {days_to_earn} days")
        if sig in ("Wait: still falling",) and checks["chk200"]: why.append("pullback with no bounce yet")
        n = {"note": ("Fails: " + "; ".join(why) + ".") if why else ("Passes all seven checks but ranks below the top 3 on score." if deep else "Passes your price and valuation checks but ranks outside the top 15 by score.")}
    rows.append({
        "symbol": it["s"], "name": it["name"], "assetClass": it["cls"], "currency": it["ccy"],
        "price": round(p, 2), "change1d": r1(100 * (p / it["prevClose"] - 1), 2),
        "return1m": pct(it["r1m"]), "return3m": pct(it["r3m"]), "return12m": pct(it["r12m"]),
        "sma20": r1(it.get("sma20"), 2), "sma50": r1(it["sma50"], 2), "sma200": r1(it["sma200"], 2),
        "vsSma50": pct(vs50), "vsSma200": pct(vs200), "rsi14": r1(rsi), "rsi5dAgo": r1(rsi5),
        "offHigh52w": pct(off_high), "high52w": r1(it["hi52"], 2), "low52w": r1(it["lo52"], 2),
        "volatility": pct(it.get("vol60"), 0),
        "trend": round(trend), "momentum": round(mom), "entry": round(entry),
        "outlook": None if outl is None else round(outl),
        "targetUpside": pct(upside), "staleTarget": stale,
        "epsRevision90d": pct(eps_rev), "revisionsUpDown30d": None if not o else f'{o["revUp30"]}/{o["revDown30"]}',
        "forwardPE": None if not o or o.get("fwdPE") is None else r1(o["fwdPE"]),
        "nextEarnings": None if not o else o.get("nextEarnings"), "daysToEarnings": days_to_earn,
        **{c: ("pass" if v else "fail") if v is not None else "n/a" for c, v in checks.items()}, "checksPassed": passed,
        "stage": it.get("stage", "Shortlist") if deep or not (checks["chk200"] and checks["chkRsi"] and checks["chkMomentum"] and checks["chkPE"] and checks["chkPEG"] and checks["chkSharpe"] and sig in ("Buy the dip", "Trend buy", "Watch"))
                 else "Passed price checks, outside top 15",
        "pe": r1(pe), "peg": r1(peg, 2), "epsGrowthNY": pct(growth), "valuation": round(val), "sharpe": r1(it.get("sharpe1y"), 2),
        "turning": turning, "score": round(score), "signal": sig, "asOf": raw["asof"][:10],
        "note": n.get("note", ""), "bull": n.get("bull", ""), "bear": n.get("bear", ""), "catalyst": n.get("catalyst", ""),
        "_score": score,
    })
    m = len(it.get("spark") or [])
    for i, c in enumerate(it.get("spark") or []):
        prices.append({"symbol": it["s"], "point": i - m + 1, "close": c})

rows.sort(key=lambda r: (r["stage"] != "Shortlist", -r["_score"]))
month = raw["asof"][:7]
eligible = lambda r: r["signal"] in ("Buy the dip", "Trend buy", "Watch") and r["checksPassed"] == 7
by = {r["symbol"]: r for r in rows}
picks = []
if lock.get("month") == month:
    # Keep this month's picks unless one breaks a hard check (below 200-DMA or bad news)
    for s_ in lock["picks"]:
        r = by.get(s_)
        if r and r["chk200"] == "pass" and r["chkPE"] == "pass":
            picks.append(s_)
    replaced = [s_ for s_ in lock["picks"] if s_ not in picks]
    for r in rows:
        if len(picks) >= 3: break
        if replaced and r["symbol"] not in picks and r["symbol"] not in lock["picks"] and eligible(r):
            picks.append(r["symbol"])
    locked_on = lock["lockedOn"] if not replaced else raw["asof"][:10]
else:
    replaced = []
    picks = [r["symbol"] for r in rows if eligible(r)][:3]
    locked_on = raw["asof"][:10]
print("skipped (under 1y history):", skipped)
json.dump({"month": month, "picks": picks, "lockedOn": locked_on, "replaced": replaced}, open(f"{out}/lock.json", "w"))
for i, r in enumerate(rows):
    r["rank"] = i + 1
    r["pick"] = picks.index(r["symbol"]) + 1 if r["symbol"] in picks else None
    r["pickedOn"] = locked_on if r["pick"] else None
    r["health"] = None if not r["pick"] else ("On track" if r["checksPassed"] == 7 else f'Watch: {7 - r["checksPassed"]} check(s) failing')
    del r["_score"]
json.dump(rows, open(f"{out}/scores.json", "w"), indent=1)
json.dump(prices, open(f"{out}/prices.json", "w"))
for r in rows:
    if r["stage"] != "Shortlist" and not r["pick"]: continue
    chk = "".join("✓" if r[c] == "pass" else "·" if r[c] == "n/a" else "✗" for c in ("chk200", "chkEarnings", "chkRsi", "chkMomentum", "chkPE", "chkPEG", "chkSharpe"))
    print(f'{r["rank"]:>2} {r["symbol"]:<7} {r["score"]:>3} pick {str(r["pick"]):>4} {chk} | tr {r["trend"]:>3} mo {r["momentum"]:>3} en {r["entry"]:>3} va {r["valuation"]:>3} pe {r["pe"]} peg {r["peg"]} ou {str(r["outlook"]):>4} | rsi {r["rsi14"]:>5} (5d {r["rsi5dAgo"]}) turn {r["turning"]!s:5} stale {r["staleTarget"]!s:5} earn {r["daysToEarnings"]} | {r["signal"]}')
