# Explaining this project: 15 likely interview questions

Short answers to learn and then say in your own words. Numbers come from the stored test run
of 21 November 2026 (see the README's Results section).

**1. What does it do, in one sentence?**
It collects free official market data every day, gives each of about 480 US stocks one call,
and, most importantly, tests whether the method behind that call actually works.

**2. What is look-ahead bias?**
Using information in a test that you wouldn't have had at the time. For example, using a
company's annual profit on the day the year ends, when the report came out two months later.
It makes a backtest look far better than real trading would. I prevent it in three ways:
- figures count only from the day after they were filed;
- economic readings are lagged until they were published;
- a test plants future data and checks that it gets caught.

**3. Why walk-forward testing instead of one train/test split?**
Markets change. Walk-forward trains only on data before each test year, then moves forward a
year and repeats. That copies what you could really have done at each point. It also shows
whether results hold across many different years or depend on one lucky period. I leave a
gap between training and test data so 20-day outcomes don't overlap.

**4. Why keep two years completely held back?**
I compared eight models. If you test eight, one will look good by luck. So the models are
chosen on the earlier years, and the winner gets one final check on the two held-back years.
Using those years to choose would make that final check meaningless.

**5. Why a t-score of 3 and not 1.96?**
1.96 is fine for a single test. But thousands of trading ideas have been tried, so some will
pass at 1.96 by chance. Harvey, Liu and Zhu argue new factors need t above 3. Hou, Xue and
Zhang found 85% of 447 published anomalies fail at that bar. A strict bar means fewer false
discoveries, at the cost of missing some weak real effects.

**6. Why did most patterns fail?**
- **Many traders already use them,** so any easy edge gets traded away.
- **Costs eat what's left:** even 0.10% per trade removes a small edge.
- **The baseline is tough:** I compared each signal with holding the *same stocks over the
  same days*, not with doing nothing, so a pattern that only rides the market's general rise
  gets no credit.

None of 64 candlestick tests, covering 716,629 signals, reached t = 3.

**7. What is survivorship bias, and how did you handle it?**
If you test only on companies that exist today, you leave out the ones that went bust. That
flatters any strategy, especially buying beaten-down stocks. I used SEC public-float filings
to rebuild which companies were large in each past year, so today's winners aren't tested
before they were big. I couldn't add companies that failed, because free data doesn't list
them. So some bias remains, and I say so.

**8. What did the stop-loss study show?**
Across 50,557 simulated trades, wider stops did better, and no stop had the best average
return (+1.34% against +0.68% for the tightest). But stops cut the worst single loss from −88%
to between −44% and −59%. And survivorship bias favours "no stop", because the collapses are missing. So
the honest answer is that it's a trade-off, not a free win.

**9. Your best model didn't pass. Isn't that a failure?**
The tool's job is to tell the truth, so finding no edge is a valid result. The chosen model's
top-ranked stocks beat the average 54% of the time against 48% for the bottom-ranked, but the
statistical test said that gap wasn't reliable. Most real strategies fail. Being able to show
*why* matters more than claiming a win.

**10. Why did all models look positive on the held-back years but not on earlier ones?**
That's a warning sign, not good news. If every model, even a weak one, does well in the same
two years, the likely cause is something about those years: the market environment, or
survivorship bias being strongest in recent data. It isn't skill. That's why the rule needs
both the early test and the held-back check to pass.

**11. How do you stop yourself editing forecasts after the fact?**
Each forecast is written before the market opens, and the database itself rejects any later
change or deletion. A trigger also refuses any forecast created after its outcome was known.
So the live track record can't be tidied up.

**12. What is calibration?**
Whether stated chances match reality. If the app says "54% chance of beating the average", then
about 54 in 100 such stocks should. I measure it on years the model never trained on, and show
the plain rate rather than the model's raw score.

**13. What would you do with paid data?**
- **Delisted stocks:** to remove the remaining survivorship bias. That's the biggest improvement.
- **Analyst forecast revisions:** one of the better-supported signals, with no free source.
- **Options data:** for the market's own estimate of how much a stock might move.
- **Full intraday data:** for proper day-trading tests, instead of one exchange's prices.

**14. What was the hardest engineering problem?**
Staying inside free limits. The database host suspended the database twice after jobs read
over a million price rows on every run. I fixed it by caching the append-only tables in
GitHub Actions and fetching only new rows. GitHub also skipped most scheduled runs, so an
outside scheduler now triggers them.

**15. What would you do differently?**
- **Write the evaluation rules first.** The t ≥ 3 bar, costs and hold-out years would come
  before any strategy. I mostly did, but one rule (the caution test) still uses t ≥ 2, which
  I'd make consistent.
- **Start the live record earlier.** It needs months of evidence, and it had run for under
  60 days at the time of writing.
