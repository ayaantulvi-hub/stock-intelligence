import { useEffect, useState } from "react";

type Level = { name: string; price: number };
type Replay = {
  replays: number;
  sessions: number;
  p_target: number;
  p_stop: number;
  p_neither: number;
  avg_r: number;
  close_low: number;
  close_high: number;
  verdict: string;
  history?: { sessions: number; triggered: number; target: number; stop: number; avg_r: number | null };
} | null;
type Setup = {
  replay?: Replay;
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
type Orb = {
  error?: string;
  scanned?: number;
  found?: number;
  setups?: (Setup & { range_high: number; range_low: number; price: number })[];
};
export type DayData = {
  orb?: Orb;
  orb_test?: Test | null;
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

const pc = (x: number) => `${(x * 100).toFixed(0)}%`;

export function ReplayBox({ replay }: { replay?: Replay }) {
  if (replay === undefined) return null;
  if (replay === null) return <p><small>Time Machine: Not verified. Fewer than 20 full past sessions to replay from.</small></p>;
  const parts = [
    { name: "Target first", share: replay.p_target, cls: "ok" },
    { name: "Stop first", share: replay.p_stop, cls: "bad" },
    { name: "Neither by close", share: replay.p_neither, cls: "" },
  ];
  return (
    <div className="replay">
      <h5>Time Machine: {replay.replays.toLocaleString()} replays of the rest of today, from the last {replay.sessions} days</h5>
      <div className="replay-bar" role="img" aria-label={parts.map((p) => `${p.name} ${pc(p.share)}`).join(", ")}>
        {parts.map((p) => (
          <span key={p.name} className={`seg ${p.cls}`} style={{ width: pc(p.share) }} />
        ))}
      </div>
      <p>
        {parts.map((p) => (
          <span key={p.name} className={p.cls}>{p.name} {pc(p.share)}. </span>
        ))}
        Average {replay.avg_r.toFixed(2)} times the risk. 9 in 10 replays closed between {replay.close_low.toFixed(2)} and {replay.close_high.toFixed(2)}.
      </p>
      <p><b>{replay.verdict}</b></p>
      {replay.history && (
        <p>
          The same rule on those {replay.history.sessions} real days: it triggered {replay.history.triggered} times, hit the target {replay.history.target}, the stop {replay.history.stop}
          {replay.history.avg_r === null ? "." : `, averaging ${replay.history.avg_r.toFixed(2)} times the risk after costs.`}
        </p>
      )}
      <small>A simulation from the stock's own recent bars, not a forecast. Method from the free day-trader-skill (MIT).</small>
    </div>
  );
}

function TestLine({ name, test }: { name: string; test?: Test | null }) {
  const proven = test?.verdict === "Edge shown in test";
  return (
    <p className={proven ? "ok" : "bad"}>
      <b>
        {name}:{" "}
        {!test
          ? "Not tested yet. Treat every setup here as a guess."
          : proven
            ? `Edge shown in test: ${test.trades} trades, ${test.mean_r?.toFixed(2)} times the risk on average after costs.`
            : `No reliable edge. In ${test.trades} past trades it made ${test.mean_r === null ? "Not verified" : test.mean_r.toFixed(2)} times the risk on average, against ${test.baseline_mean_r === null ? "Not verified" : test.baseline_mean_r.toFixed(2)} for coin-flip trades. Practice only.`}
      </b>
      {test && ` Tested on ${test.data_from} to ${test.data_to}.`}
    </p>
  );
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
        Why: price reached <b>{setup.level}</b>, confirmed by <b>{setup.confirmed_by}</b>{setup.ticker === "SPY" || setup.ticker === "QQQ" ? ", then a 1-minute signal" : ""}.
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
      <ReplayBox replay={setup.replay} />
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
  const today = data?.window ? windowState(now, data.window.start, data.window.end) : null;
  const upcoming = data?.next_window ? windowState(now, data.next_window.start, data.next_window.end) : null;
  const open = Boolean(today?.open && data?.market_open);
  return (
    <section>
      <h2>Day trading: S&amp;P 500 (SPY) and Nasdaq (QQQ)</h2>
      <TestLine name="TJR rules" test={test} />
      <TestLine name="Opening-range breakout" test={data?.orb_test} />
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
      {data?.orb && (
        <div className="orders">
          <h3>Opening-range breakouts across {data.orb.scanned ?? 0} stocks</h3>
          {data.orb.error ? (
            <p className="bad">Scanner unavailable: {data.orb.error}</p>
          ) : (
            <>
              <p className="plain">
                <b>{data.orb.found ?? 0} stocks</b> have closed a 5-minute bar outside their first 15 minutes' range today. The {data.orb.setups?.length ?? 0} most traded are shown. Stop at the middle of the range, target 2 times the risk.
              </p>
              {data.orb.setups?.map((setup) => (
                <SetupCard
                  key={setup.ticker}
                  setup={{ ...setup, level: `the opening range ${setup.range_low.toFixed(2)} to ${setup.range_high.toFixed(2)}`, confirmed_by: "a 5-minute close outside it", result: null, exit: null, r: null, reward_to_risk: 2 }}
                  account={Number(account)}
                  share={data.risk_share ?? 0.01}
                />
              ))}
            </>
          )}
        </div>
      )}
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
