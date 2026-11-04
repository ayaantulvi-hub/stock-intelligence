import { useEffect, useState, type FormEvent } from "react";
import { IdeasPanel } from "./ForecastPanel";

const NOT_VERIFIED = "Not verified";

function useData<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    fetch(url)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setData)
      .catch(() => setFailed(true));
  }, [url]);
  return { data, setData, failed };
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (response.status !== 200) throw new Error(result.detail ?? "Could not save.");
  return result;
}

const money = (value: number | null) =>
  value === null ? NOT_VERIFIED : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const pct = (value: number | null) =>
  value === null ? NOT_VERIFIED : `${(value * 100).toFixed(1)}%`;
const Failed = () => <p className="bad">Could not load this. Not verified.</p>;

export function WatchButton({ ticker }: { ticker: string }) {
  const { data, setData } = useData<string[]>("/api/watchlist");
  const watching = data?.includes(ticker) ?? false;
  const toggle = async () => {
    setData(await send<string[]>(`/api/watchlist/${ticker}`, watching ? "DELETE" : "PUT"));
  };
  return (
    <p>
      <button onClick={toggle}>{watching ? "Stop alerts for this stock" : "Get alerts for this stock"}</button>
    </p>
  );
}

type Row = {
  ticker: string;
  name: string;
  last_close: number;
  rank: number | null;
  p_up: number;
  action: string;
  lean: string;
};
const COLUMNS: [keyof Row, string][] = [
  ["ticker", "Stock"],
  ["last_close", "Close"],
  ["lean", "Model leans"],
  ["rank", "20-day rank"],
  ["p_up", "Chance up tomorrow"],
];

export function Screener({ onOpen }: { onOpen: (ticker: string) => void }) {
  const { data, failed } = useData<Row[]>("/api/screener");
  const [filter, setFilter] = useState("");
  const [lean, setLean] = useState("All");
  const [sort, setSort] = useState<keyof Row>("rank");
  const [ascending, setAscending] = useState(false);
  if (failed) return <Failed />;
  if (!data || data.length === 0) return null;
  const text = filter.toLowerCase();
  const rows = data
    .filter((row) => lean === "All" || row.lean === lean)
    .filter(
      (row) => row.ticker.toLowerCase().includes(text) || row.name.toLowerCase().includes(text),
    )
    .sort((a, b) => {
      const order = (a[sort] ?? -1) < (b[sort] ?? -1) ? -1 : 1;
      return ascending ? order : -order;
    });
  const click = (key: keyof Row) => {
    setAscending(sort === key ? !ascending : key === "ticker");
    setSort(key);
  };
  return (
    <section>
      <h2>All stocks</h2>
      <p>
        The model's unproven lean for each stock. Tap a heading to sort, or a stock to open it.
      </p>
      <div className="screener-tools">
        <input
          aria-label="Filter stocks"
          placeholder="Filter"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <div className="tabs" role="group" aria-label="Lean">
          {["All", "Buy", "Mixed", "Sell"].map((name) => (
            <button key={name} aria-pressed={name === lean} onClick={() => setLean(name)}>
              {name}
            </button>
          ))}
        </div>
      </div>
      <div className="scroll">
        <table className="screener">
          <thead>
            <tr>
              {COLUMNS.map(([key, label]) => (
                <th key={key}>
                  <button onClick={() => click(key)}>{label}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 100).map((row) => (
              <tr key={row.ticker}>
                <td>
                  <button className="link" onClick={() => onOpen(row.ticker)}>
                    {row.ticker}
                  </button>
                </td>
                <td>{row.last_close.toFixed(2)}</td>
                <td className={row.lean === "Buy" ? "ok" : row.lean === "Sell" ? "bad" : ""}>
                  {row.lean}
                </td>
                <td>{row.rank === null ? NOT_VERIFIED : Math.round(row.rank * 100)}</td>
                <td>{pct(row.p_up)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

type Mood = {
  mood: string;
  meaning: string;
  vix: number | null;
  credit_spread: number | null;
  above_200: number | null;
  stocks_measured: number;
  next_fed: string | null;
};

export function MarketMood() {
  const { data } = useData<Mood>("/api/market-mood");
  if (!data) return null;
  return (
    <section>
      <h2>Market mood: {data.mood}</h2>
      <p className="so-what">
        <b>What this means for you:</b> {data.meaning}
      </p>
      <div className="glance">
        <div>
          <small>Fear gauge (VIX)</small>
          <strong>{data.vix ?? NOT_VERIFIED}</strong>
        </div>
        <div>
          <small>Stocks above their 200-day average</small>
          <strong>{pct(data.above_200)}</strong>
        </div>
        <div>
          <small>Corporate borrowing premium</small>
          <strong>{data.credit_spread === null ? NOT_VERIFIED : `${data.credit_spread}%`}</strong>
        </div>
        <div>
          <small>Next Fed decision</small>
          <strong>{data.next_fed ?? NOT_VERIFIED}</strong>
        </div>
      </div>
      <small>VIX below 20 is usually called calm, and 30 or above stressed.</small>
    </section>
  );
}

type Portfolio = {
  worth: number;
  cost: number;
  profit: number;
  risks: string[];
  sectors: { sector: string; share: number }[];
  holdings: {
    ticker: string;
    sector: string;
    shares: number;
    buy_price: number;
    price: number | null;
    worth: number | null;
    profit: number | null;
    share_of_total: number | null;
  }[];
};

export function PortfolioPage() {
  const { data, failed } = useData<Portfolio>("/api/portfolio");
  if (failed) return <Failed />;
  if (!data) return <p>Loading…</p>;
  if (data.holdings.length === 0) {
    return <p>No holdings yet. Open a stock and tap "I own this".</p>;
  }
  return (
    <section>
      <h2>My portfolio</h2>
      <div className="glance">
        <div>
          <small>Worth</small>
          <strong>{money(data.worth)}</strong>
        </div>
        <div>
          <small>Cost</small>
          <strong>{money(data.cost)}</strong>
        </div>
        <div>
          <small>Profit or loss</small>
          <strong className={data.profit >= 0 ? "ok" : "bad"}>{money(data.profit)}</strong>
        </div>
      </div>
      {data.risks.length > 0 && (
        <ul>
          {data.risks.map((risk) => (
            <li key={risk} className="bad">
              {risk}
            </li>
          ))}
        </ul>
      )}
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Stock</th>
              <th>Sector</th>
              <th>Worth</th>
              <th>Profit</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((row) => (
              <tr key={row.ticker}>
                <td>{row.ticker}</td>
                <td>{row.sector}</td>
                <td>{money(row.worth)}</td>
                <td>{money(row.profit)}</td>
                <td>{pct(row.share_of_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

type Entry = {
  created_at: string;
  ticker: string;
  decision: string;
  reason: string;
  price: number;
  change_percent: number;
};

export function JournalPage() {
  const { data, setData, failed } = useData<Entry[]>("/api/journal");
  const [form, setForm] = useState({ ticker: "", decision: "buy", reason: "" });
  const [error, setError] = useState<string | null>(null);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setData(await send<Entry[]>("/api/journal", "POST", form));
      setError(null);
      setForm({ ticker: "", decision: "buy", reason: "" });
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not save.");
    }
  };
  if (failed) return <Failed />;
  return (
    <section>
      <h2>Trade journal</h2>
      <p>Write down why before you decide, then see what happened. Entries can't be edited.</p>
      <form onSubmit={save} className="inputs">
        <label>
          Ticker
          <input required value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value })} />
        </label>
        <label>
          Decision
          <select value={form.decision} onChange={(e) => setForm({ ...form, decision: e.target.value })}>
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
            <option value="hold">Hold</option>
            <option value="skip">Skip</option>
          </select>
        </label>
        <label>
          Why?
          <input required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        </label>
        <button type="submit">Save</button>
      </form>
      {error && <p className="bad">{error}</p>}
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Stock</th>
              <th>Decision</th>
              <th>Price then</th>
              <th>Change since</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((row) => (
              <tr key={row.created_at}>
                <td>{row.ticker}</td>
                <td>{row.decision}</td>
                <td>{row.price.toFixed(2)}</td>
                <td>{row.change_percent.toFixed(1)}%</td>
                <td>{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function AlertsPage() {
  const { data, failed } = useData<{ created_at: string; kind: string; message: string }[]>("/api/alerts");
  if (failed) return <Failed />;
  return (
    <section>
      <h2>Alerts</h2>
      <p>For stocks you own or chose alerts for. Each one is also sent as a GitHub notification.</p>
      {data?.length === 0 && <p>No alerts yet.</p>}
      <ul>
        {data?.map((row) => (
          <li key={`${row.created_at}${row.message}`}>
            {new Date(row.created_at).toLocaleDateString()}: {row.message}
          </li>
        ))}
      </ul>
    </section>
  );
}

type Reliability = {
  days: number;
  grade: string;
  overall: { count: number; brier: number | null; baseline: number | null; range_hit: number | null };
  calibration: { said: number; happened: number; count: number }[];
  recent: Record<string, { count: number; brier: number | null; baseline: number | null }>;
  sectors: { sector: string; count: number; brier: number | null; baseline: number | null }[];
};

export function ReliabilityPage() {
  const { data, failed } = useData<Reliability>("/api/reliability");
  if (failed) return <Failed />;
  if (!data) return <p>Loading…</p>;
  const score = (value: number | null) => (value === null ? NOT_VERIFIED : value.toFixed(3));
  return (
    <section>
      <h2>How reliable has it been?</h2>
      <div className="action">
        <small>Live grade, from {data.days} trading days</small>
        <strong>{data.grade}</strong>
        <p>A grade needs at least 60 trading days of locked forecasts.</p>
      </div>
      <div className="glance">
        <div>
          <small>Forecasts scored</small>
          <strong>{data.overall.count}</strong>
        </div>
        <div>
          <small>Score (lower is better)</small>
          <strong>{score(data.overall.brier)}</strong>
        </div>
        <div>
          <small>Guessing</small>
          <strong>{score(data.overall.baseline)}</strong>
        </div>
        <div>
          <small>Range hit rate (target 90%)</small>
          <strong>{pct(data.overall.range_hit)}</strong>
        </div>
      </div>
      <h3>Said against happened</h3>
      {data.calibration.length === 0 ? (
        <p>{NOT_VERIFIED}: nothing has been scored yet.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>When it said</th>
                <th>It happened</th>
                <th>Cases</th>
              </tr>
            </thead>
            <tbody>
              {data.calibration.map((row) => (
                <tr key={row.said}>
                  <td>{pct(row.said)}</td>
                  <td>{pct(row.happened)}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h3>Recent trend</h3>
      <ul>
        {Object.entries(data.recent).map(([days, row]) => (
          <li key={days}>
            Last {days} days: {score(row.brier)} against {score(row.baseline)} for guessing
          </li>
        ))}
      </ul>
      <h3>By sector</h3>
      <ul>
        {data.sectors.map((row) => (
          <li key={row.sector}>
            {row.sector}: {score(row.brier)} against {score(row.baseline)} ({row.count} forecasts)
          </li>
        ))}
      </ul>
      <IdeasPanel part="record" />
    </section>
  );
}
