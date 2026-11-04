import { useEffect, useState } from "react";

const NOT_VERIFIED = "Not verified";
type Source = { tag: string; value: number; period_end: string; form: string; url: string };
type Metric = { name: string; value: number | null; kind: string; sources: Source[] };
type Case = { name: string; value: number; against_price: number };
type Trade = {
  owner: string;
  title: string | null;
  transaction_date: string;
  code: string;
  shares: number;
  price: number | null;
  planned_sale: boolean;
  document_url: string;
};
type Report = {
  available: boolean;
  price: number | null;
  metrics: Metric[];
  history: { period_end: string; revenue: number | null; net_income: number | null; url: string | null }[];
  cases: Case[];
  assumptions: Record<string, number>;
  valuation_inputs?: Source[];
  insider_trades: Trade[];
};

const INPUTS: [string, string][] = [
  ["bear_growth", "Bear growth"],
  ["base_growth", "Base growth"],
  ["bull_growth", "Bull growth"],
  ["discount_rate", "Yearly return you require"],
  ["terminal_growth", "Growth after 10 years"],
];

function money(value: number) {
  const size = Math.abs(value);
  if (size >= 1e12) return `$${(value / 1e12).toFixed(2)} trillion`;
  if (size >= 1e9) return `$${(value / 1e9).toFixed(1)} billion`;
  if (size >= 1e6) return `$${(value / 1e6).toFixed(1)} million`;
  return `$${value.toFixed(2)}`;
}

function show(metric: Metric) {
  if (metric.value === null) return NOT_VERIFIED;
  if (metric.kind === "money") return money(metric.value);
  if (metric.kind === "percent") return `${(metric.value * 100).toFixed(1)}%`;
  return metric.value.toFixed(2);
}

function Links({ sources }: { sources: Source[] }) {
  return (
    <>
      {sources.map((source) => (
        <a key={`${source.tag}${source.period_end}`} href={source.url} target="_blank" rel="noreferrer">
          {source.form} {source.period_end}{" "}
        </a>
      ))}
    </>
  );
}

export default function LongTermPanel({ ticker }: { ticker: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [changes, setChanges] = useState<Record<string, number>>({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams(
      Object.entries(changes).map(([key, value]) => [key, String(value)]),
    );
    fetch(`/api/stocks/${encodeURIComponent(ticker)}/valuation?${query}`)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then((body) => {
        if (active) {
          setReport(body);
          setFailed(false);
        }
      })
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, [ticker, changes]);

  if (failed) return <p className="bad">Long-term view failed to load. Not verified.</p>;
  if (!report) return <p>Loading…</p>;
  if (!report.available) {
    return <p>Not verified: no SEC company figures are stored for this stock yet.</p>;
  }
  return (
    <div>
      <h3>Bull, Base and Bear value per share</h3>
      <p>
        What the shares would be worth if these assumptions came true. These are calculations, not
        predictions. Change any number to see the effect.
      </p>
      {report.cases.length === 0 ? (
        <p>Not verified: a value can't be worked out, usually because cash flow is negative.</p>
      ) : (
        <div className="glance">
          {report.cases.map((item) => (
            <div key={item.name}>
              <small>{item.name}</small>
              <strong>${item.value.toFixed(2)}</strong>
              <small>
                {(item.against_price * 100).toFixed(0)}% against ${report.price?.toFixed(2)}
              </small>
            </div>
          ))}
        </div>
      )}
      <div className="inputs">
        {INPUTS.map(([key, label]) => (
          <label key={key}>
            {label} (%)
            <input
              type="number"
              step="0.5"
              value={((changes[key] ?? report.assumptions[key]) * 100).toFixed(1)}
              onChange={(event) => {
                const value = Number(event.target.value) / 100;
                if (!Number.isNaN(value)) setChanges({ ...changes, [key]: value });
              }}
            />
          </label>
        ))}
      </div>
      {report.valuation_inputs && (
        <small>
          From filings: <Links sources={report.valuation_inputs} />
        </small>
      )}
      <h3>The business in numbers</h3>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Measure</th>
              <th>Latest</th>
              <th>Source filing</th>
            </tr>
          </thead>
          <tbody>
            {report.metrics.map((metric) => (
              <tr key={metric.name}>
                <td>{metric.name}</td>
                <td>{show(metric)}</td>
                <td>
                  <Links sources={metric.sources} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {report.history.length > 0 && (
        <>
          <h3>Results by year</h3>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Year to</th>
                  <th>Revenue</th>
                  <th>Net income</th>
                  <th>Filing</th>
                </tr>
              </thead>
              <tbody>
                {report.history.map((row) => (
                  <tr key={row.period_end}>
                    <td>{row.period_end}</td>
                    <td>{row.revenue === null ? NOT_VERIFIED : money(row.revenue)}</td>
                    <td>{row.net_income === null ? NOT_VERIFIED : money(row.net_income)}</td>
                    <td>
                      {row.url ? (
                        <a href={row.url} target="_blank" rel="noreferrer">
                          Open
                        </a>
                      ) : (
                        NOT_VERIFIED
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <h3>Insider trades on the open market</h3>
      {report.insider_trades.length === 0 ? (
        <p>{NOT_VERIFIED}: none stored yet.</p>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Who</th>
                <th>Action</th>
                <th>Shares</th>
                <th>Price</th>
                <th>Planned sale</th>
              </tr>
            </thead>
            <tbody>
              {report.insider_trades.map((trade) => (
                <tr key={`${trade.document_url}${trade.shares}`}>
                  <td>{trade.transaction_date}</td>
                  <td>
                    <a href={trade.document_url} target="_blank" rel="noreferrer">
                      {trade.owner}
                    </a>
                  </td>
                  <td>{trade.code === "P" ? "Bought" : "Sold"}</td>
                  <td>{trade.shares.toLocaleString()}</td>
                  <td>{trade.price === null ? NOT_VERIFIED : trade.price.toFixed(2)}</td>
                  <td>{trade.planned_sale ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
