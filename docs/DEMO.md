# Demo

The live site is private and password protected. These screenshots come from a local copy
running on **synthetic data**: 40 invented companies with random prices, built by
[`demo/`](../demo). No real prices, headlines or holdings appear. The red banner marks every
image.

| Page | What it shows |
|---|---|
| [Trading](screenshots/1-trading.png) | The model's top 10, labelled "Unproven ranking", with the price not to pay above, the stop and the sell-by date |
| [Long-term](screenshots/2-long-term.png) | Best to buy and stocks to sell, from company checks |
| [My portfolio](screenshots/3-my-portfolio.png) | Two invented demo positions, each with its Keep or Sell call |
| [How reliable?](screenshots/4-how-reliable.png) | Factor-family tests, calibration, model comparison and the track record |
| [Data](screenshots/5-data.png) | The market check and economy readings, each with its source and date |
| [A stock page](screenshots/6-stock-page.png) | One call, the chance of beating the average stock, and why it is unproven |

Because the data is random, every test on these pages correctly finds no edge. That is the
point of the demo: the system says "no reliable edge" rather than inventing one.

## Walkthrough script (60–90 seconds)

Record it on the demo data above, so no private numbers appear. The times are a guide.

**0:00 – 0:10. The problem.**
"I built this to answer one question honestly: does a trading idea actually work, or does it
only look like it works? It collects free official data on about 480 US companies every day
and gives each one a single call."

**0:10 – 0:25. Trading page.**
"This is today's top 10. Notice the red line: 'Unproven ranking.' The model ranks stocks, but
it hasn't passed its own test, so the app says so instead of pretending."

**0:25 – 0:45. How reliable? page.**
"This is the part I care about most. Every idea is tested on years the model never saw,
after trading costs, and it needs a t-score of 3, not the usual 2, because when you test many
ideas some will look good by luck. Here eight models compete, and none passes. On my real
data, 64 candlestick-pattern tests over 700,000 signals also found nothing."

**0:45 – 1:00. A stock page.**
"For one stock you get a single call and a plain chance of beating the average stock. 50% is
a coin flip, and the page says when the evidence is that weak. Every number links to where
it came from."

**1:00 – 1:15. Data page and close.**
"Economic readings come from official sources such as the Federal Reserve, each dated. If
data is missing, it says 'Not verified' instead of guessing. The biggest thing I learned is
that most published strategies don't survive a fair test, and a tool should be built to
tell you that."

## What not to show when recording

- **The live site:** it holds real holdings.
- **Real prices or headlines from the private site:** the data providers' terms don't allow
  republishing them.
