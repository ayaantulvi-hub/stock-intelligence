import { useEffect, useState } from "react";

type Level = { name: string; price: number };
type Setup = {
  ticker: string;
  side: "long" | "short";
  level: string;
  confirmed_by: string;
  entered_at: string;
  entry: number;
  stop: number;
  target: number;
  reward_to_risk: number | null;
  result: string | null;
  exit: number | null;
  r: number | null;
};
type Stock = {
  ticker: string;
  price: number;
  levels: Level[];
  step: { touched?: { level: string; side: string } | null; confirmed?: string | null };
  setups: Setup[];
};
type Test = {
  run_at: string;
  data_from: string;
  data_to: string;
  trades: number;
  mean_r: number | null;
  win_rate: number | null;
  baseline_mean_r: number | null;
  verdict: string;
};
export type DayData = {
  error?: string;
  test: Test | null;
  session?: string;
  window?: { start: string; end: string };
  next_window?: { start: string; end: string };
  market_open?: boolean;
  stale?: boolean;
  last_bar?: string;
  source?: string;
  retrieved_at?: string;
  risk_share?: number;
  stocks?: Stock[];
};

const ACCOUNT_KEY = "account-size";
const clockTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

function savedAccount() {
  try {
    return window.localStorage.getItem(ACCOUNT_KEY) ?? "";
  } catch {
    return "";
  }
}

export function windowState(now: number, start: string, end: string) {
  const from = Date.parse(start);
  const to = Date.parse(end);
  if (now < from) return { open: false, text: `Opens in ${Math.ceil((from - now) / 60000)} min, at ${clockTime(start)} your time.` };
  if (now < to) return { open: true, text: `Open now. Closes at ${clockTime(end)} your time.` };
  return { open: false, text: "Closed for today." };
}

export function stepText(stock: Stock, open: boolean) {
  if (stock.setups.some((setup) => setup.result === null)) return "Trade open. Follow the plan below.";
  const touched = stock.step.touched;
  if (!open) return "Outside the trading window, so no new setups.";
  if (!touched) return "Step 1 of 3: waiting for price to reach a key level.";
  const way = touched.side === "short" ? "sell short" : "buy";
  if (!stock.step.confirmed) return `Step 2 of 3: price reached ${touched.level}. Waiting for a 5-minute signal to ${way}.`;
  return `Step 3 of 3: confirmed by ${stock.step.confirmed}. Waiting for the 1-minute entry signal to ${way}.`;
}

export function shares(account: number, share: number, entry: number, stop: number) {
  const risk = Math.abs(entry - stop);
  return risk > 0 && account > 0 ? Math.floor((account * share) / risk) : null;
}

function SetupCard({ setup, account, share }: { setup: Setup; account: number; share: number }) {
  const buy = setup.side === "long";
  const count = shares(account, share, setup.entry, setup.stop);
  const finished = setup.result !== null;
  return (
    <div className={`ticket action ${buy ? "buy" : "sell"}`}>
      <h4>
        {buy ? "Buy" : "Sell short"} {setup.ticker} at {clockTime(setup.entered_at)}
        {finished && ` — finished: ${setup.result}, ${setup.r === null ? "" : `${setup.r.toFixed(2)} times the risk`}`}
      </h4>
      <p>
        Why: price reached <b>{setup.level}</b>, confirmed by <b>{setup.confirmed_by}</b>, then a 1-minute signal.
      </p>
      {!finished && (
        <table>
          <tbody>
            <tr><td>Order tab</td><td><b>Market</b></td></tr>
            <tr><td>Side</td><td><b>{buy ? "Buy" : "Sell"}</b></td></tr>
            <tr><td>Shares</td><td><b>{count === null ? "Enter your account size above" : count}</b> ({(share * 100).toFixed(0)}% of your account at risk)</td></tr>
            <tr><td>Take profit price (switch on)</td><td><b>{setup.target.toFixed(2)}</b></td></tr>
            <tr><td>Stop loss price (switch on)</td><td><b>{setup.stop.toFixed(2)}</b></td></tr>
            <tr><td>Signal price</td><td>{setup.entry.toFixed(2)}. Skip if the live price has already moved past the halfway point to the target.</td></tr>
          </tbody>
        </table>
      )}
      <small>Close it yourself by 3:55pm New York time if neither price is hit.</small>
    </div>
  );
}

export function DayTradingPage() {
  const [data, setData] = useState<DayData | null>(null);
  const [failed, setFailed] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [account, setAccount] = useState(savedAccount);
  useEffect(() => {
    const load = () =>
      fetch("/api/day-trading")
        .then((response) => {
          if (response.status !== 200) throw new Error();
          return response.json();
        })
        .then((body) => {
          setData(body);
          setFailed(false);
        })
        .catch(() => setFailed(true));
    load();
    const timer = setInterval(() => {
      setNow(Date.now());
      load();
    }, 60000);
    return () => clearInterval(timer);
  }, []);
  const change = (value: string) => {
    setAccount(value);
    try {
      window.localStorage.setItem(ACCOUNT_KEY, value);
    } catch {
      // Works without saving.
    }
  };
  const test = data?.test;
  const proven = test?.verdict === "Edge shown in test";
  const today = data?.window ? windowState(now, data.window.start, data.window.end) : null;
  const upcoming = data?.next_window ? windowState(now, data.next_window.start, data.next_window.end) : null;
  const open = Boolean(today?.open && data?.market_open);
  return (
    <section>
      <h2>Day trading: S&amp;P 500 (SPY) and Nasdaq (QQQ)</h2>
      <p className={proven ? "ok" : "bad"}>
        <b>
          {!test
            ? "Not tested yet. Treat every setup here as a guess."
            : proven
              ? `Edge shown in test: ${test.trades} trades, ${test.mean_r?.toFixed(2)} times the risk on average after costs.`
              : `No reliable edge. In ${test.trades} past trades it made ${test.mean_r === null ? "Not verified" : test.mean_r.toFixed(2)} times the risk on average, against ${test.baseline_mean_r === null ? "Not verified" : test.baseline_mean_r.toFixed(2)} for coin-flip trades. Practice only.`}
        </b>
        {test && ` Tested on ${test.data_from} to ${test.data_to}.`}
      </p>
      <p className="plain">
        <b>Trading window:</b> {open ? today?.text : upcoming?.text ?? "Not verified"} At most 2 trades a day.
      </p>
      <label className="inputs">
        Account size in $
        <input type="number" min="0" value={account} onChange={(e) => change(e.target.value)} />
      </label>
      {failed && <p className="bad">Could not load day trading. Refresh to try again.</p>}
      {data?.error && <p className="bad">Live prices unavailable: {data.error}. Nothing below is shown until this is fixed.</p>}
      {data?.stale && <p className="bad">The latest prices are more than 10 minutes old, so no setups are shown.</p>}
      {data?.stocks?.map((stock) => (
        <div key={stock.ticker} className="orders">
          <h3>
            {stock.ticker} {stock.price.toFixed(2)}
          </h3>
          <p className="plain"><b>{stepText(stock, open)}</b></p>
          {stock.setups.map((setup) => (
            <SetupCard key={setup.entered_at} setup={setup} account={Number(account)} share={data.risk_share ?? 0.01} />
          ))}
          <details>
            <summary>Key levels today ({stock.levels.length})</summary>
            <table>
              <tbody>
                {stock.levels.map((level) => (
                  <tr key={level.name} className={level.price > stock.price ? "row-sell" : "row-buy"}>
                    <td>{level.name}</td>
                    <td>{level.price.toFixed(2)}</td>
                    <td>{level.price > stock.price ? "Above: look to sell short here" : "Below: look to buy here"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </div>
      ))}
      {data?.source && (
        <small>
          Prices: {data.source}, last minute {data.last_bar ? clockTime(data.last_bar) : "Not verified"}, fetched{" "}
          {data.retrieved_at ? clockTime(data.retrieved_at) : "Not verified"}. Updates every minute while this page is open.
        </small>
      )}
      <details>
        <summary>The rules (from TJR's method)</summary>
        <ol>
          <li>Key levels are set before the open: previous day high, low and 50%, the last 1-hour and 4-hour swing high and low, and the pre-market high and low.</li>
          <li>Only trade 9:50 to 10:30am New York time.</li>
          <li>When price reaches a level, wait for a 5-minute signal: a candle closing past the last swing, a broken fair value gap, or SPY and QQQ disagreeing at a swing.</li>
          <li>Then enter on a 1-minute signal the same way. Stop at the extreme since the level was reached. Target the next level at least as far as the stop.</li>
          <li>Risk 1% of your account a trade. Close everything by 3:55pm New York time.</li>
        </ol>
      </details>
    </section>
  );
}
