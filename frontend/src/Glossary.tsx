const TERMS: [string, string][] = [
  ["Stock price", "What one share of a company last sold for. It moves as people buy and sell."],
  [
    "Candlestick",
    "One bar on the chart, usually one day. The thick part runs from the opening price to the closing price. The thin lines show the day's highest and lowest prices. Green means it closed higher than it opened, and red means lower.",
  ],
  ["Volume", "How many shares changed hands. Busy days often come with bigger news."],
  [
    "Moving average",
    "The average closing price over a set number of days, updated daily. It smooths out daily noise so you can see the direction. The 50-day shows the recent direction, and the 200-day shows the long-term one.",
  ],
  [
    "Support",
    "A price where a stock has stopped falling and bounced before. Think of a floor. Floors can break, and it can fall straight through.",
  ],
  [
    "Resistance",
    "A price where a stock has stopped rising and turned back before. Think of a ceiling. Ceilings can break too.",
  ],
  [
    "Breakout",
    "When the price closes above a ceiling. A breakdown is the opposite: it closes below a floor.",
  ],
  [
    "RSI",
    "A score from 0 to 100 showing how fast a stock has risen or fallen lately. Above 70 is called overbought, meaning it rose quickly. Below 30 is called oversold, meaning it fell quickly. Neither means it must turn around.",
  ],
  [
    "MACD",
    "Compares a short-term average with a longer-term one to show whether recent movement is speeding up or slowing down.",
  ],
  [
    "Golden cross",
    "When the 50-day average rises above the 200-day average. A death cross is when it drops below.",
  ],
  [
    "Double top or bottom",
    "A double top is two peaks at about the same price, then a fall through the low between them. A double bottom is the upside-down version.",
  ],
  [
    "Head and shoulders",
    "Three peaks with the middle one highest, then a fall through the line under them. The inverse version is the same shape upside down.",
  ],
  [
    "Triangle",
    "Prices squeeze between a flat line and a sloping one. An ascending triangle has a flat ceiling and rising floors. A descending one has a flat floor and falling ceilings.",
  ],
  [
    "Momentum",
    "The tendency of stocks that have been rising to keep rising for a while, and of falling ones to keep falling. It often fails.",
  ],
  [
    "Volatility",
    "How much a price swings. A more volatile stock can gain or lose more in a day.",
  ],
  ["Percentile", "Where a stock ranks among those covered. 90 means higher than 90% of them."],
  [
    "Baseline",
    "The simple alternative to beat, such as just holding the stock. A signal that can't beat this isn't useful.",
  ],
  [
    "No reliable edge",
    "Testing could not show that the signal or model does better than the simple alternative. So the app makes no call.",
  ],
  ["Backtest", "Trying a rule on past prices to see how it would have done."],
  [
    "Cancelled at",
    "The price where a signal's idea stops being valid. Below that price for a bullish signal, or above it for a bearish one, the signal has failed.",
  ],
  ["Buy candidate", "A stock the tested model ranks in its top 10% for the next 20 days. It isn't a guarantee."],
];

export default function Glossary() {
  return (
    <details className="glossary">
      <summary>New to this? What these words mean</summary>
      <dl>
        {TERMS.map(([term, meaning]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{meaning}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
