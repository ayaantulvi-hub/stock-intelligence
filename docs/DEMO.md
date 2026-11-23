# Demo

The live dashboard is private and password protected, because it charts series derived from
licensed prices. These screenshots come from a local copy running on **synthetic data** built
by [`demo/`](../demo): 40 invented companies with random prices. The red banner marks every
image.

- [Full page, desktop](screenshots/quant-lab-desktop.png)
- [Opening screen, phone](screenshots/quant-lab-phone.png)

On random data there is nothing real to find, so every trading study reports "No reliable
edge". The two simple Value at Risk models pass here, because random data has none of the
waves of volatility that real markets do. On real prices those two models are rejected.

## What the page shows

- **The score.** "N tests. K passed." is counted from the stored verdicts, not typed in.
- **A switch at the top: Plain English or Quant detail.** Every study has both. Plain English
  says what the idea is and what happened, in everyday words. Quant detail gives the formulas,
  the test statistics in a table, and how to read them. Both take every number from the
  stored results, and any sentence that depends on a result is chosen by the verdict.
- **Each study:** the question, a chart with a hover readout and a table view, three key
  figures, every verdict, and the actual function from the repository that produced it. A
  test fails if a code panel ever stops matching the real file.
- **What the statistics actually said:** one line per study, passed or failed.
- **Data:** how many stocks and price rows the results rest on, each feed's last run, and the
  limits.

## Walkthrough script (60–90 seconds)

Record it on the demo data, so no licensed prices appear. The times are a guide.

**0:00 – 0:12. The point.**
"This is my Quant Lab. I took five well-known ideas from quant finance and built each from
scratch in Python, then tested them the way a sceptical reviewer would: on years they weren't
designed on, after trading costs, with a t-score of 3 to pass."

**0:12 – 0:25. The score.**
"The headline is counted from the stored results. On my real data, one of nine tests
passed. Every failure is listed here too, because a tool that only shows wins is not
evidence of anything."

**0:25 – 0:45. Value at Risk.**
"The clearest finding. All three risk models got the number of bad days about right, but the
two that treat every past day equally were caught by a second test. Their bad days came in
runs, exactly when risk was rising. The model that weights recent days more passed both
tests."

**0:45 – 1:05. Pairs trading.**
"Pairs trading made up to 11% a year in the original 1960s-to-2002 study. On 2011 to 2026,
after costs and a borrowing fee, it had no reliable edge. The recent years look better, but
choosing the best-looking stretch after seeing the results is exactly the mistake I built
this to avoid."

**1:05 – 1:20. How it's built.**
"Under each chart: the settings, the period and the papers it follows. Data comes from the
SEC, the Federal Reserve and licensed price feeds, updated every hour. There are automatic
tests, including one that plants future data to prove the backtest can't cheat."
