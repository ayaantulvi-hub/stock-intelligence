import { leanRow } from "./leanRow";
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
  ["rank", "Upside rank, 20 days"],
];

export function Screener({ onOpen }: { onOpen: (ticker: string) => void }) {
  const { data, failed } = useData<Row[]>("/api/screener");
  const [filter, setFilter] = useState("");
  const [lean, setLean] = useState("Buy");
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
    <details className="fold">
      <summary>All stocks</summary>
      <p>
        Most upside first, as ranked by the model, where 100 is its top pick. Unproven. Tap a
        heading to sort, or a stock to open it.
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
              <tr key={row.ticker} className={leanRow(row.lean)}>
                <td>
                  <button className="link" onClick={() => onOpen(row.ticker)}>
                    {row.ticker}
                  </button>
                </td>
                <td>{row.last_close.toFixed(2)}</td>
                <td>
                  {row.lean}
                </td>
                <td>{row.rank === null ? NOT_VERIFIED : Math.round(row.rank * 100)}</td>
                <td>{pct(row.p_up)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
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
    <details className="fold">
      <summary>Market mood: {data.mood}</summary>
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
    </details>
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

type Change = {
  ticker: string;
  topic: string;
  was: string;
  now: string;
  why: string;
  tone: string;
  action: string;
  yours: boolean;
};
type Changes = {
  latest: string | null;
  previous: string | null;
  decisions: Change[];
  details: Change[];
};

function ChangeRows({ rows, onOpen }: { rows: Change[]; onOpen?: (ticker: string) => void }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Stock</th>
            <th>What changed</th>
            <th>Was</th>
            <th>Now</th>
            <th>What to do</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.ticker}${row.topic}${row.now}`}
              className={row.tone === "buy" ? "row-buy" : row.tone === "sell" ? "row-sell" : ""}
            >
              <td>
                <button className="link" onClick={() => onOpen?.(row.ticker)}>
                  {row.ticker}
                </button>
              </td>
              <td>{row.topic}</td>
              <td>{row.was || "None"}</td>
              <td>
                <b>{row.now}</b>
              </td>
              <td>
                <b>{row.action}</b>
                <small>{row.why}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Markets = {
  markets: { name: string; ticker: string; price: number | null; change: number | null; at: string | null }[];
  versus: { since: string; yours: number; market: number } | null;
};
const signed = (value: number) => `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;

export function MarketStrip() {
  const { data, failed } = useData<Markets>("/api/markets");
  if (failed || !data) return null;
  const at = data.markets.find((item) => item.at)?.at;
  return (
    <section className="strip">
      <div className="glance">
        {data.markets.map((item) => (
          <div key={item.ticker}>
            <small>
              {item.name} ({item.ticker})
            </small>
            <strong className={item.change === null ? "" : item.change >= 0 ? "ok" : "bad"}>
              {item.change === null ? NOT_VERIFIED : signed(item.change)}
            </strong>
            <small>{item.price === null ? "" : item.price.toFixed(2)}</small>
          </div>
        ))}
      </div>
      {data.versus && (
        <p className="plain">
          Since {data.versus.since}: your stocks{" "}
          <b className={data.versus.yours >= 0 ? "ok" : "bad"}>{signed(data.versus.yours)}</b>, the
          S&P 500 <b className={data.versus.market >= 0 ? "ok" : "bad"}>{signed(data.versus.market)}</b>.
        </p>
      )}
      <small>
        Today's change for funds that track each market. Updated hourly
        {at && `, last at ${new Date(at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`}
        , so it trails your live chart. It shows where markets are, not where they're going.
      </small>
    </section>
  );
}

export function countdown(milliseconds: number) {
  if (milliseconds <= 0) return null;
  const minutes = Math.floor(milliseconds / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}d ${hours % 24}h ${minutes % 60}m`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  return `${minutes}m ${Math.floor(milliseconds / 1000) % 60}s`;
}

export function NextDecision() {
  const { data } = useData<{ next: string; last: string | null }>("/api/next-decision");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, []);
  if (!data) return null;
  const due = new Date(data.next);
  const left = countdown(due.getTime() - now);
  return (
    <p className="timer">
      <small>Next decisions in</small> <strong>{left ?? "due now, refresh in a few minutes"}</strong>{" "}
      <small>
        {due.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}. The
        run can start late.{" "}
        {data.last && `Last set: ${new Date(data.last).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}.`}
      </small>
    </p>
  );
}

export function WhatChanged({ onOpen }: { onOpen?: (ticker: string) => void }) {
  const { data } = useData<Changes>("/api/changes");
  if (!data) return null;
  const mine = data.decisions.filter((row) => row.yours).length;
  return (
    <section className={`changes ${mine > 0 ? "urgent" : ""}`}>
      <h2>
        {data.decisions.length === 0
          ? "No decisions changed"
          : `${data.decisions.length} decision${data.decisions.length === 1 ? "" : "s"} changed${
              mine > 0 ? `, ${mine} on stocks you own` : ""
            }`}
      </h2>
      {!data.previous && <p>Decision changes appear once there are two forecast days to compare.</p>}
      {data.decisions.length > 0 && <ChangeRows rows={data.decisions} onOpen={onOpen} />}
      {data.details.length > 0 && (
        <details className="fold">
          <summary>Smaller changes ({data.details.length})</summary>
          <small>These don't change a buy, wait or sell decision.</small>
          <ChangeRows rows={data.details} onOpen={onOpen} />
        </details>
      )}
    </section>
  );
}

type Big = {
  cards: {
    title: string;
    reading: string;
    state: string;
    meaning: string;
    source: string;
    url: string;
    date: string | null;
  }[];
  actions: { published: string; kind: string; title: string; topic: string | null; url: string }[];
  warnings: { subject: string; bad: number; outlets: number; title: string; url: string }[];
  news: {
    market: NewsGroup[];
    industries: NewsGroup[];
    companies: { subject: string; title: string; url: string; domain: string }[];
  };
};
export type NewsGroup = {
  subject: string;
  tone: string;
  articles: { title: string; url: string; domain: string; seen_at: string }[];
};

function NewsList({ group }: { group: NewsGroup }) {
  return (
    <ul>
      {group.articles.map((item) => (
        <li key={item.url}>
          <a href={item.url} target="_blank" rel="noreferrer">
            {item.title}
          </a>{" "}
          <small>
            {item.domain}, {item.seen_at.slice(0, 10)}
          </small>
        </li>
      ))}
    </ul>
  );
}

function NewsLevel({ title, groups }: { title: string; groups: NewsGroup[] }) {
  return (
    <>
      <h4>{title}</h4>
      {groups.length === 0 && <p>No headlines stored yet.</p>}
      {groups.map((group) => (
        <details className="fold" key={group.subject}>
          <summary>
            {group.subject}:{" "}
            <span className={group.tone.includes("negative") ? "bad" : group.tone.includes("positive") ? "ok" : ""}>
              {group.tone}
            </span>
          </summary>
          <NewsList group={group} />
        </details>
      ))}
    </>
  );
}

export function StockNews({ ticker }: { ticker: string }) {
  const { data, failed } = useData<NewsGroup & { industry: NewsGroup | null; market: NewsGroup[] }>(
    `/api/stocks/${encodeURIComponent(ticker)}/news`,
  );
  if (failed) return <p className="bad">Could not load the news. Refresh to try again.</p>;
  return (
    <details className="fold">
      <summary>News{data ? ` (${data.articles.length} on this company)` : ""}</summary>
      <h4>This company</h4>
      {data?.articles.length === 0 && <p>No headlines naming this company in the last 7 days.</p>}
      {data && <NewsList group={data} />}
      {data?.industry && data.industry.articles.length > 0 && (
        <>
          <h4>Its industry: {data.industry.subject}</h4>
          <NewsList group={data.industry} />
        </>
      )}
      <small>Headlines and links only. Bad news from several outlets can stop a buy.</small>
    </details>
  );
}

export function BigPicture() {
  const { data, failed } = useData<Big>("/api/big-picture");
  if (failed) return <Failed />;
  if (!data) return <p>Loading…</p>;
  return (
    <section>
      <h2>The big picture</h2>
      <p>
        What's happening in the economy and government, and what it means for you. The model tests
        these readings each week. They only count in its ranking if they earn their place.
      </p>
      {data.cards.map((card) => (
        <div
          key={card.title}
          className={`horizon ${card.state === "good" ? "buy" : card.state === "bad" ? "sell" : ""}`}
        >
          <h4>{card.title}</h4>
          <p>
            <b>{card.reading}</b>
          </p>
          <p>{card.meaning}</p>
          <small>
            <a href={card.url} target="_blank" rel="noreferrer">
              {card.source}
            </a>
            {card.date && `, ${card.date}`}
          </small>
        </div>
      ))}
      <h3>News warnings now</h3>
      <small>
        Several outlets carrying bad news on the same subject. These stop buys in that group and
        flag anything you own. The rule reads words, so check the headline yourself.
      </small>
      {data.warnings.length === 0 ? (
        <p>No warnings right now.</p>
      ) : (
        <ul>
          {data.warnings.map((item) => (
            <li key={item.subject} className="bad">
              <b>{item.subject}:</b> {item.bad} bad headlines from {item.outlets} outlets.{" "}
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.title}
              </a>
            </li>
          ))}
        </ul>
      )}
      <h3>News by how far it reaches</h3>
      <small>
        Headlines from major outlets and company announcements. Mood is a rough word count.
      </small>
      <NewsLevel title="Affects the whole market" groups={data.news.market} />
      <NewsLevel title="Affects one industry" groups={data.news.industries} />
      <details className="fold">
        <summary>Affects one company ({data.news.companies.length})</summary>
        <ul>
          {data.news.companies.map((item) => (
            <li key={`${item.subject}${item.url}`}>
              <b>{item.subject}: </b>
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.title}
              </a>{" "}
              <small>{item.domain}</small>
            </li>
          ))}
        </ul>
      </details>
      <h3>Recent presidential actions</h3>
      <small>From the Federal Register, the government's official journal. Ceremonial items are left out.</small>
      {data.actions.length === 0 ? (
        <p>None stored in the last 60 days.</p>
      ) : (
        <ul>
          {data.actions.map((item) => (
            <li key={item.url}>
              {item.published} {item.topic && <b>{item.topic}: </b>}
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.title}
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Holding = {
  ticker: string;
  name: string;
  price: number | null;
  buy_price: number;
  sell_by: string | null;
  call: string;
  reason: string;
  kind: string;
};

export function HoldingsToday({ onOpen }: { onOpen?: (ticker: string) => void }) {
  const { data } = useData<Holding[]>("/api/holdings-today");
  if (!data || data.length === 0) return null;
  const selling = data.filter((row) => row.call === "Sell now").length;
  const checking = data.filter((row) => row.call === "Check the news").length;
  return (
    <section className="orders">
      <h2>Your stocks today</h2>
      <p className="plain">
        <b>
          {selling === 0
            ? checking === 0
              ? "Keep everything."
              : `Keep everything, and check the news on ${checking}.`
            : `Sell ${selling} now, keep the rest.`}
        </b> Checked
        every update. These are rules, not a promise of what comes next.
      </p>
      <div className="scroll">
        <table>
          <tbody>
            {data.map((row) => (
              <tr key={row.ticker} className={leanRow(row.call === "Sell now" ? "Sell" : row.call === "Keep" ? "Buy" : row.call === "Check the news" ? "Hold off" : "")}>
                <td>
                  <button className="link" onClick={() => onOpen?.(row.ticker)}>
                    {row.ticker}
                  </button>
                </td>
                <td><b>{row.call}</b></td>
                <td>{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

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
      <HoldingsToday />
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

type Misses = {
  checked: number;
  reasons: { reason: string; count: number }[];
  recent: { ticker: string; target_session: string; reason: string; change_percent: number }[];
};

function WhyWrong() {
  const { data } = useData<Misses>("/api/misses");
  if (!data) return null;
  const total = data.reasons.reduce((sum, row) => sum + row.count, 0);
  return (
    <>
      <h3>Why forecasts were wrong</h3>
      {total === 0 ? (
        <p>Nothing to explain yet. Reasons appear once forecasts have been scored.</p>
      ) : (
        <>
          <p>
            {total} of {data.checked} scored forecasts were wrong. These are the likeliest reasons
            from stored records. "No cause is stored" means it's unknown, not that there wasn't one.
          </p>
          <div className="scroll">
            <table>
              <tbody>
                {data.reasons.map((row) => (
                  <tr key={row.reason}>
                    <td>{row.reason}</td>
                    <td>{row.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details className="fold">
            <summary>Latest misses</summary>
            <ul>
              {data.recent.map((row) => (
                <li key={`${row.ticker}${row.target_session}`}>
                  {row.target_session} {row.ticker} {row.change_percent.toFixed(1)}%: {row.reason}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </>
  );
}

export function ReliabilityPage() {
  const { data, failed } = useData<Reliability>("/api/reliability");
  const { data: check } = useData<{
    checked: number;
    flagged: number;
    problems: { ticker: string; detail: string }[];
  }>("/api/data-check");
  if (failed) return <Failed />;
  if (!data) return <p>Loading…</p>;
  const score = (value: number | null) => (value === null ? NOT_VERIFIED : value.toFixed(3));
  return (
    <section>
      <h2>How reliable has it been?</h2>
      <div className="action">
        <small>Live grade, from {data.days} trading days</small>
        <strong>{data.grade}</strong>
        <p>The first grade appears after 20 trading days and updates daily. Before day 60 it is only an early sign.</p>
      </div>
      <WhyWrong />
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
      {check && (
        <>
          <h3>Company data check</h3>
          <p>
            {check.checked - check.flagged} of {check.checked} companies passed the automatic
            checks. This catches impossible or out-of-date figures. It can't prove a figure is
            right.
          </p>
          {check.problems.length > 0 && (
            <details>
              <summary>See the {check.flagged} flagged companies</summary>
              <ul>
                {check.problems.map((row) => (
                  <li key={`${row.ticker}${row.detail}`}>
                    {row.ticker}: {row.detail}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      <IdeasPanel part="record" />
    </section>
  );
}
