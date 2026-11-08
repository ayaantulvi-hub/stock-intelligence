import { useEffect, useState } from "react";

function useJson<T>(url: string) {
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
  return { data, failed };
}

type Trade = {
  member: string;
  owner: string | null;
  ticker: string;
  asset: string;
  action: string;
  trade_date: string | null;
  filed_date: string | null;
  amount: string | null;
  days_to_file: number | null;
  url: string;
  owned?: boolean;
};

function TradeRows({ trades }: { trades: Trade[] }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr><th>Stock</th><th>Who</th><th>Did</th><th>Traded</th><th>Reported</th><th>Amount</th><th>Source</th></tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={`${t.url}-${i}`} className={t.action === "Buy" ? "row-buy" : t.action.includes("ale") ? "row-sell" : ""}>
              <td>
                <b>{t.ticker}</b>
                {t.owned ? " (you own this)" : ""}
                {t.asset.includes("[OP]") ? " options" : ""}
              </td>
              <td>{t.member}{t.owner && t.owner !== "Member" ? ` (${t.owner.toLowerCase()})` : ""}</td>
              <td>{t.action}</td>
              <td>{t.trade_date ?? "Not verified"}</td>
              <td>{t.filed_date ?? "Not verified"}{t.days_to_file !== null ? `, ${t.days_to_file} days later` : ""}</td>
              <td>{t.amount ?? "Not verified"}</td>
              <td><a href={t.url} target="_blank" rel="noreferrer">Report</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CongressTrades() {
  const { data, failed } = useJson<{ trades: Trade[]; reports_read: number; reports_unread: number; newest_filing: string | null; note: string }>("/api/congress");
  if (failed) return <p className="bad">Could not load Congress trades.</p>;
  if (!data) return null;
  return (
    <section>
      <h2>Congress trades in our stocks</h2>
      <p>{data.note} Read {data.reports_read} reports{data.reports_unread ? `, ${data.reports_unread} couldn't be read` : ""}. Newest filing: {data.newest_filing ?? "Not verified"}.</p>
      {data.trades.length === 0 ? <p>None in the last 60 days.</p> : <TradeRows trades={data.trades} />}
    </section>
  );
}

type Short = {
  settlement_date: string;
  short_shares: number;
  avg_daily_volume: number | null;
  days_to_cover: number | null;
  change?: number;
  source_url: string;
};

export function StockCrowd({ ticker }: { ticker: string }) {
  const { data, failed } = useJson<{ short_interest: Short | null; congress: Trade[] }>(`/api/stocks/${ticker}/crowd`);
  if (failed) return <p className="bad">Could not load short interest and Congress trades.</p>;
  if (!data) return null;
  const s = data.short_interest;
  return (
    <section>
      <h3>Bets against it, and Congress trades</h3>
      {s ? (
        <p>
          <b>{(s.short_shares / 1e6).toFixed(1)} million shares</b> sold short on {s.settlement_date}
          {s.change !== undefined ? `, ${s.change >= 0 ? "up" : "down"} ${Math.abs(s.change * 100).toFixed(0)}% since the report before` : ""}.{" "}
          {s.days_to_cover !== null && `At normal trading, buying them all back would take ${s.days_to_cover.toFixed(1)} days. `}
          Lots of short selling means many traders expect a fall, and if the price rises instead, their buying back can push it up fast. Shown for context: not tested as a signal.{" "}
          <a href={s.source_url} target="_blank" rel="noreferrer">FINRA</a>
        </p>
      ) : (
        <p>Short interest: Not verified.</p>
      )}
      {data.congress.length === 0 ? <p>No House member reported trading it in the last year.</p> : <TradeRows trades={data.congress} />}
    </section>
  );
}

type Override = { rule: string; run_at: string; blocked: number; blocked_mean: number | null; others: number; others_mean: number | null; verdict: string };
type Checks = {
  conflicts: { ticker: string; market_date: string; detail: string }[];
  last_check: string | null;
  overrides: Override[];
};

const pct = (x: number | null) => (x === null ? "Not verified" : `${(x * 100).toFixed(2)}%`);

export function SourceChecks() {
  const { data, failed } = useJson<Checks>("/api/checks");
  if (failed) return <p className="bad">Could not load the data checks.</p>;
  if (!data) return null;
  return (
    <section>
      <h2>Do the sources agree?</h2>
      <p>
        Each day, prices from Tiingo are compared with Alpaca, and the S&amp;P 500 and Dow from FRED with the funds that track them. A disagreement is shown with both numbers, never averaged away.
        Last check: {data.last_check ? new Date(data.last_check).toLocaleString() : "Not verified"}.
      </p>
      {data.conflicts.length === 0 ? (
        <p className="ok">{data.last_check ? "No disagreements in the last week." : "Not checked yet."}</p>
      ) : (
        <ul>
          {data.conflicts.map((c, i) => (
            <li key={i} className="bad"><b>{c.ticker} {c.market_date}:</b> {c.detail}</li>
          ))}
        </ul>
      )}
      <h2>Do the caution rules help?</h2>
      <p>The expert checks and news warnings only ever stop a buy. This compares the stocks they stopped with the rest, 20 trading days later.</p>
      {data.overrides.length === 0 ? (
        <p>Not tested yet.</p>
      ) : (
        <table>
          <thead><tr><th>Rule</th><th>Stopped</th><th>Their average</th><th>Others</th><th>Their average</th><th>Result</th></tr></thead>
          <tbody>
            {data.overrides.map((o) => (
              <tr key={o.rule} className={o.verdict.startsWith("Helped") ? "row-buy" : o.verdict.startsWith("Hurt") ? "row-sell" : ""}>
                <td>{o.rule}</td><td>{o.blocked}</td><td>{pct(o.blocked_mean)}</td><td>{o.others}</td><td>{pct(o.others_mean)}</td><td><b>{o.verdict}</b></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
