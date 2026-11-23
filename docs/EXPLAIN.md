# Explaining this project: 15 likely interview questions

Short answers to learn and then say in your own words. Numbers come from the stored run of
23 November 2026: [QUANT.md](QUANT.md) has the full tables and
[RESEARCH.md](RESEARCH.md) the two written-up findings.

**1. What does it do, in one sentence?**
It takes five well-known quant ideas, builds each from scratch in Python, and tests them on
16 years of daily prices for 480 large US companies, after costs, on years they weren't
designed on, with a t-score of 3 to pass.

**2. What did you find?**
13 tests, 1 passed: the EWMA Value at Risk model. Every trading idea, including trend
following, pairs trading and four kinds of volatility targeting, showed no reliable edge after
costs. That is the expected result for well-known, free-data ideas, and the project reports it
rather than hiding it.

**3. What is look-ahead bias, and how do you stop it?**
Using information you wouldn't have had at the time. It makes backtests look far better than
real trading. I stop it in four ways:
- a position decided at one day's close only earns the next day's return;
- an automatic test flips the sign of every later return and checks that earlier decisions
  don't change, and a planted cheating rule fails it;
- company sizes from SEC filings count only from the April after the year they describe;
- models that are fitted, like GARCH, refit only on data before each refit date.

**4. Why a t-score of 3 and not 1.96?**
1.96 is fine for one test. But thousands of trading ideas have been tried, so some pass 1.96
by luck. Harvey, Liu and Zhu argue a new factor needs a t-score above 3. I use 3 for every
idea, and I set it before seeing any result.

**5. Why Newey-West standard errors?**
Daily returns aren't independent: volatile days cluster, and some tests use overlapping
21-day windows. Ordinary standard errors assume independence, so they're too small and
t-scores too big. Newey-West corrects for that.

**6. Why keep two years held back?**
To check a result on data that played no part in judging it. A pass needs t ≥ 3 on the
earlier years and a positive result on the last two calendar years.

**7. What is survivorship bias, and is it still in your data?**
Testing only on companies that survived, which flatters results because the failures are
missing. I reduce it by letting a stock trade only in years when SEC filings show it was large
at the time. It isn't removed: the list is still today's companies, because the free data has
no list of delisted stocks. I say so on every results page.

**8. Your Value at Risk models got the number of bad days right. Why were two rejected?**
Counting breaches is the Kupiec test. It's blind to timing. The Christoffersen test checks
whether one breach makes the next more likely. With historical simulation, the day after a
breach had a 16.6% chance of another, against 5% expected. The bad days came in runs, exactly
when risk was highest, which is when a risk model matters most.

**9. Why does EWMA pass when historical simulation fails?**
Historical simulation treats every one of the last 500 days equally, so after a shock it takes
weeks to catch up. EWMA puts about 6% of its weight on yesterday, so its estimate rises within
days. It had a breach rate of 5.4% and a bunching-test p-value of 0.063, so it passes both
tests.

**10. You added GARCH with fat tails. Why didn't it pass?**
It had the best timing of all five models, but too many breaches: 6.5% against 5%. One
mechanical reason: at the 95% level, a fat-tailed Student-t with the same variance puts its
5% cut-off nearer zero than a normal curve does (about −1.59 against −1.64 standard
deviations at 6 degrees of freedom), so the line sits slightly too shallow. I reported that
rather than adjusting it, because changing a model after seeing its test result is the
mistake the test exists to catch.

**11. How does pairs trading work, and why did it fail?**
Find two stocks that move together, and when they drift apart, buy the cheaper and sell the
pricier, betting the gap closes. I tested two ways of choosing pairs: the distance method from
Gatev, Goetzmann and Rouwenhorst, and cointegration. The better one made 3.9% a year before
costs, but trading and borrowing costs took 1.5%, and its Sharpe ratio was 0.22 ± 0.25. For a
bet meant to be market-neutral, it also fell 43.6% at its worst.

**12. Pairs trading did well on the held-back years. Why not claim that?**
Its Sharpe ratio was 1.39 on 2025–26, but −0.82 on 2011–15. Picking the good stretch after
seeing the results is data snooping. The rule was set in advance: the full earlier period must
pass too, and it didn't (t = 0.31).

**13. Volatility targeting cut the worst fall from −38.8% to −21.8%. Isn't that a success?**
It's real, but it's close to mechanical: volatility persists, so exposure is already low when
a sell-off deepens. The question Moreira and Muir ask is whether it earns more for its risk,
measured by alpha against just holding the market. The best version's alpha t-score was 1.12,
far from 3. I also used only past data to set the target. Cederburg and colleagues found that,
done in real time like this, volatility management often harms performance.

**14. 12 of your 13 tests failed. Isn't the project a failure?**
No. The aim was to build a test strict enough to tell real effects from luck, and to show it
working. A tool that only reports wins isn't evidence of anything. The one pass also shows the test
isn't simply rejecting everything.

**15. What would you do with more time or paid data?**
Add delisted companies to remove survivorship bias, use intraday data so entries and exits
aren't limited to closing prices, and measure trading costs per stock instead of assuming
0.10%. I'd also add an Expected Shortfall backtest, because Value at Risk says how often a
loss is exceeded but not by how much.

## How I checked the numbers

- The metrics are hand-written and checked in the tests against the independent `empyrical`
  library.
- The GARCH model is tested on simulated data with a known volatility path, and tracks it with
  a correlation above 0.9.
- 90 automated tests run on every change, including the look-ahead check for every strategy.

## For a CV or application

Each claim below is traceable to the stored results.

- Built a quantitative research lab in Python that tests five classic strategies on 16 years
  of daily prices for 480 US companies, with walk-forward rules, trading costs, Newey-West
  t-scores and a t ≥ 3 bar set in advance.
- Found that only 1 of 13 tests passed: an EWMA Value at Risk model. Two standard models got
  the number of bad days right but were rejected because breaches clustered, with a 16.6%
  chance of a breach the day after one, against 5% expected.
- Engineered automatic data collection from the SEC, the Federal Reserve and licensed price
  feeds, with 90 automated tests, including one that plants future data to prove the backtests
  can't cheat.

**One line for a personal statement:**
"I built a lab to test well-known trading strategies the way a sceptical reviewer would, and
the most useful result was a failure: 12 of 13 tests found no reliable edge, which taught me
how easily patterns that look real turn out to be luck."
