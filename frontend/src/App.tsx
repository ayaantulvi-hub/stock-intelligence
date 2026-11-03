import { useEffect, useState, type FormEvent } from "react";
import ChartPanel from "./ChartPanel";

type Status = {
  database: { state: string };
  migrations: { state: string };
  worker: { state: string };
};
type Feed = {
  feed: string;
  source: string;
  status: string;
  message: string | null;
  last_run: string | null;
  records_added: number | null;
};
type Listing = { ticker: string; name: string; exchange: string };
type Provenance = {
  source: string;
  source_url: string;
  retrieved_at: string;
  data_status: string;
};
type Bar = Provenance & {
  market_date: string;
  market_timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};
type Filing = Provenance & { form: string; filing_date: string; document_url: string };
type Stock = {
  ticker: string;
  name: string;
  stale: boolean;
  latest_expected_session: string;
  bars: Bar[];
  filings: Filing[];
};
type Economic = Provenance & {
  series_id: string;
  observation_date: string;
  value: number | null;
};

const LABELS: Record<string, string> = {
  ok: "OK",
  error: "Error",
  partial: "Partly failed",
  running: "Running",
  stale: "Stale",
  never_run: "Never run",
  not_verified: "Not verified",
};
const NOT_VERIFIED = "Not verified";

const label = (state: string) => LABELS[state] ?? NOT_VERIFIED;
const when = (value: string | null) => (value ? new Date(value).toLocaleString() : NOT_VERIFIED);

async function getJson<T>(url: string, allowed: number[] = [200]): Promise<T> {
  const response = await fetch(url);
  if (!allowed.includes(response.status)) throw new Error(String(response.status));
  return response.json();
}

function State({ state }: { state: string }) {
  return <span className={state === "ok" ? "ok" : "bad"}>{label(state)}</span>;
}

function StockView({ stock }: { stock: Stock }) {
  return (
    <section>
      <h2>
        {stock.ticker} · {stock.name}
      </h2>
      {stock.stale && (
        <p className="bad">
          Stale: expected prices for {stock.latest_expected_session}. Do not rely on this data.
        </p>
      )}
      <ChartPanel ticker={stock.ticker} />
      <h3>Recent prices (raw, not adjusted)</h3>
      {stock.bars.length === 0 ? (
        <p>{NOT_VERIFIED}</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Open</th>
                <th>High</th>
                <th>Low</th>
                <th>Close</th>
                <th>Volume</th>
                <th>Market time</th>
                <th>Retrieved</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {stock.bars.map((bar) => (
                <tr key={bar.market_date}>
                  <td>{bar.market_date}</td>
                  <td>{bar.open.toFixed(2)}</td>
                  <td>{bar.high.toFixed(2)}</td>
                  <td>{bar.low.toFixed(2)}</td>
                  <td>{bar.close.toFixed(2)}</td>
                  <td>{bar.volume.toLocaleString()}</td>
                  <td>{when(bar.market_timestamp)}</td>
                  <td>{when(bar.retrieved_at)}</td>
                  <td>{bar.data_status}</td>
                  <td>{bar.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h3>Filings</h3>
      {stock.filings.length === 0 ? (
        <p>{NOT_VERIFIED}</p>
      ) : (
        <ul>
          {stock.filings.map((filing) => (
            <li key={filing.document_url}>
              <a href={filing.document_url} target="_blank" rel="noreferrer">
                {filing.form}, filed {filing.filing_date}
              </a>{" "}
              · {filing.source}, retrieved {when(filing.retrieved_at)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [economic, setEconomic] = useState<Economic[]>([]);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Listing[] | null>(null);
  const [stock, setStock] = useState<Stock | null>(null);
  const [stockError, setStockError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        // A 503 still carries a valid status body, which is shown as it is.
        setStatus(await getJson<Status>("/api/status", [200, 503]));
        setFeeds(await getJson<Feed[]>("/api/feeds"));
        setEconomic(await getJson<Economic[]>("/api/economic"));
        setFailed(false);
      } catch {
        setStatus(null);
        setFeeds([]);
        setEconomic([]);
        setFailed(true);
      }
    };
    load();
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, []);

  const search = async (event: FormEvent) => {
    event.preventDefault();
    setStock(null);
    setStockError(null);
    try {
      setResults(await getJson<Listing[]>(`/api/stocks?q=${encodeURIComponent(query)}`));
    } catch {
      setResults(null);
      setStockError("Search failed. Results are not verified.");
    }
  };

  const open = async (ticker: string) => {
    setStockError(null);
    try {
      setStock(await getJson<Stock>(`/api/stocks/${encodeURIComponent(ticker)}`));
    } catch {
      setStock(null);
      setStockError(`Could not load ${ticker}. Data is not verified.`);
    }
  };

  return (
    <main>
      <h1>Stock Intelligence</h1>
      <p>Verified data and chart signals. Forecasts are not built yet.</p>
      {failed && <p className="bad">Cannot reach the API. Status is not verified.</p>}
      {!failed && !status && <p>Checking…</p>}

      <form onSubmit={search}>
        <input
          aria-label="Search stocks"
          placeholder="Ticker or company"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit">Search</button>
      </form>
      {stockError && <p className="bad">{stockError}</p>}
      {results?.length === 0 && <p>Not verified: no covered stock matches.</p>}
      {results && results.length > 0 && !stock && (
        <ul>
          {results.map((item) => (
            <li key={item.ticker}>
              <button className="link" onClick={() => open(item.ticker)}>
                {item.ticker}
              </button>{" "}
              {item.name}
            </li>
          ))}
        </ul>
      )}
      {stock && <StockView stock={stock} />}

      {status && (
        <section>
          <h2>System</h2>
          <dl>
            <div>
              <dt>Database</dt>
              <dd>
                <State state={status.database.state} />
              </dd>
            </div>
            <div>
              <dt>Database schema</dt>
              <dd>
                <State state={status.migrations.state} />
              </dd>
            </div>
            <div>
              <dt>Scheduled updates</dt>
              <dd>
                <State state={status.worker.state} />
              </dd>
            </div>
          </dl>
        </section>
      )}

      {feeds.length > 0 && (
        <section>
          <h2>Data feeds</h2>
          <dl>
            {feeds.map((feed) => (
              <div key={feed.feed}>
                <dt>
                  {feed.feed} · {feed.source}
                  <small>
                    Last run {when(feed.last_run)}
                    {feed.message ? `: ${feed.message}` : ""}
                  </small>
                </dt>
                <dd>
                  <State state={feed.status} />
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {economic.length > 0 && (
        <section>
          <h2>Economic data</h2>
          <dl>
            {economic.map((row) => (
              <div key={row.series_id}>
                <dt>
                  {row.series_id} · {row.observation_date}
                  <small>
                    {row.source}, retrieved {when(row.retrieved_at)}
                  </small>
                </dt>
                <dd>{row.value ?? NOT_VERIFIED}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      <p>
        <small>
          This product uses the FRED® API but is not endorsed or certified by the Federal Reserve
          Bank of St. Louis.
        </small>
      </p>
    </main>
  );
}
