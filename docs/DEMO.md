# Demo

The live dashboard is private and password protected, because it charts series derived from
licensed prices. These screenshots come from a local copy running on **synthetic data** built
by [`demo/`](../demo): 40 invented companies with random prices. The red banner marks every
image.

- [Overview](screenshots/quant-lab-overview.png)
- [A study: pairs trading](screenshots/quant-lab-pairs.png)
- [Value at Risk, with the quant detail open](screenshots/quant-lab-var-quant.png)

On random data there is nothing real to find, so every trading study reports "No reliable
edge". The two simple Value at Risk models pass here, because random data has none of the
waves of volatility that real markets do. On real prices those two models are rejected.

## What the page shows

It is laid out like a market terminal, for a desktop screen: a status bar on top, a list of
screens on the left (keys 0 to 6 switch between them), and one screen at a time, with every
piece of information in its own labelled panel.

- **Overview.** "N tests. K passed." is counted from the stored verdicts. Below it: every test
  in one table with the statistic that decided it, and one line per study on what it found.
- **Each study.** The question; three key figures; a chart with a hover readout and a table
  view; every verdict with its deciding statistic; an explanation with a switch between
  **Plain English** and **Quant detail**; the actual function from the repository; and the
  papers it follows. Every number comes from the stored results, and any sentence that
  depends on a result is chosen by the verdict. A test fails if a code panel ever stops
  matching the real file.
- **Data.** How many stocks and price rows the results rest on, each feed's last run, and the
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
"Every study has a plain-English explanation, a switch to the full quant detail, and the
exact code that produced the result. Data comes from the
SEC, the Federal Reserve and licensed price feeds, updated every hour. There are automatic
tests, including one that plants future data to prove the backtest can't cheat."
