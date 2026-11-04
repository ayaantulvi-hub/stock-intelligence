import { useEffect, useState } from "react";
import ChecklistPanel from "./ChecklistPanel";
import PositionPanel from "./PositionPanel";

const NOT_VERIFIED = "Not verified";
type Driver = { factor: string; percentile: number };
type Forecast = {
  action: string;
  target_session: string;
  as_of_session: string;
  created_at: string;
  last_close: number;
  p_up: number;
  p_flat: number;
  p_down: number;
  range_low: number;
  range_high: number;
  rank_20d: number | null;
  next_day_edge: boolean;
  confidence: string;
  drivers: Driver[];
};
type Factor = {
  id: string;
  name: string;
  group: string;
  source: string;
  status: string;
  effect: string | null;
  url: string | null;
  high_means: string | null;
};
type Ideas = {
  target_session: string | null;
  edge: boolean;
  buy: { ticker: string; name: string }[];
  sell: { ticker: string; name: string }[];
};
type Track = {
  scored: number;
  written: number;
  brier: number | null;
  baseline_brier: number | null;
  range_hit_rate: number | null;
  evaluations: {
    model: string;
    edge: boolean;
    t_stat: number;
    test_days: number;
    top_minus_bottom: number | null;
  }[];
};

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const MEANINGS: Record<string, string> = {
  "Buy candidate": "Ranked in the top 10% for the next 20 days by a model that passed testing.",
  "Sell candidate": "Ranked in the bottom 10% for the next 20 days by a model that passed testing.",
  "No action": "The tested model does not rank this stock near the top or bottom.",
  "No reliable edge":
    "No buy or sell call. Testing has not shown this model beats simply holding, so any call would be a guess.",
};

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (response.status !== 200) throw new Error(String(response.status));
  return response.json();
}

function FactorTable({ forecast, factors }: { forecast: Forecast | null; factors: Factor[] }) {
  const readings = new Map(forecast?.drivers.map((item) => [item.factor, item.percentile]));
  const ordered = [...factors].sort(
    (a, b) =>
      Math.abs((readings.get(b.id) ?? 50) - 50) - Math.abs((readings.get(a.id) ?? 50) - 50),
  );
  return (
    <>
      <h3>Every factor for this company</h3>
      <small>Percentile: 100 is highest of all covered stocks, 50 is the middle.</small>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Group</th>
              <th>Factor</th>
              <th>Percentile</th>
              <th>Meaning when high</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((factor) => (
              <tr key={factor.id}>
                <td>{factor.group}</td>
                <td>{factor.name}</td>
                <td>{readings.get(factor.id) ?? NOT_VERIFIED}</td>
                <td>{factor.high_means ?? factor.status}</td>
                <td>
                  {factor.url ? (
                    <a href={factor.url} target="_blank" rel="noreferrer">
                      {factor.source}
                    </a>
                  ) : (
                    factor.source
                  )}
                  {factor.effect && <small>{factor.effect}</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

type Lean = {
  factor: string;
  name: string;
  percentile: number;
  lean: string;
  evidence: string;
  proven: boolean;
};
type Leans = {
  factors: Lean[];
  proven_buy: number;
  proven_sell: number;
  paper_buy: number;
  paper_sell: number;
  overall: { decision: string; lean: string; proven: boolean; rank: number | null };
};

function LeanTable({ leans }: { leans: Leans }) {
  return (
    <>
      <h3>Which factors lean buy or sell</h3>
      <div className="glance">
        <div>
          <small>Proven, lean buy</small>
          <strong className="ok">{leans.proven_buy}</strong>
        </div>
        <div>
          <small>Proven, lean sell</small>
          <strong className="bad">{leans.proven_sell}</strong>
        </div>
        <div>
          <small>Unproven, lean buy</small>
          <strong>{leans.paper_buy}</strong>
        </div>
        <div>
          <small>Unproven, lean sell</small>
          <strong>{leans.paper_sell}</strong>
        </div>
      </div>
      <div className={`action ${leans.overall.proven ? (leans.overall.lean === "Buy" ? "buy" : "sell") : ""}`}>
        <small>Overall decision</small>
        <strong>{leans.overall.decision}</strong>
        <p>
          {leans.overall.proven
            ? "This passed testing."
            : `The model weighing all factors leans ${leans.overall.lean}${
                leans.overall.rank === null
                  ? ""
                  : `, ranking this stock higher than ${Math.round(leans.overall.rank * 100)}% of those covered for the next 20 days`
              }. This lean is unproven, so don't treat it as a decision.`}
        </p>
      </div>
      <small>
        Proven means the factor passed testing in this app. Unproven only reflects what a paper
        found, so don't count it the same way. The overall decision comes from the tested model, not from counting these rows.
      </small>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Factor</th>
              <th>Percentile</th>
              <th>Leans</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {leans.factors.map((row) => (
              <tr key={row.factor}>
                <td>{row.name}</td>
                <td>{row.percentile}</td>
                <td className={row.lean === "Buy" ? "ok" : row.lean === "Sell" ? "bad" : ""}>
                  {row.lean}
                </td>
                <td>{row.evidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

type Line = {
  topic: string;
  tone: string;
  text: string;
  why: string;
  evidence: string;
  on_chart: string;
};

function Story({ lines, chartFirst = false }: { lines: Line[]; chartFirst?: boolean }) {
  return (
    <div className="story">
      {lines.map((line) => (
        <div key={line.topic} className={`tone-${line.tone}`}>
          <small>{line.topic}</small>
          <strong>{line.text}</strong>
          <span>{line.why}</span>
          <details open={chartFirst}>
            <summary>How we know</summary>
            <p>{line.evidence}</p>
            <p>{line.on_chart}</p>
          </details>
        </div>
      ))}
    </div>
  );
}

export function ChartReading({ ticker }: { ticker: string }) {
  const [lines, setLines] = useState<Line[]>([]);
  useEffect(() => {
    getJson<Line[]>(`/api/stocks/${encodeURIComponent(ticker)}/story`)
      .then(setLines)
      .catch(() => setLines([]));
  }, [ticker]);
  if (lines.length === 0) return null;
  return (
    <>
      <h3>What this chart is showing</h3>
      <Story lines={lines.filter((line) => line.topic !== "Why this call")} chartFirst />
    </>
  );
}

export function FactorsPanel({ ticker }: { ticker: string }) {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [factors, setFactors] = useState<Factor[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    Promise.all([
      getJson<Forecast | null>(`/api/stocks/${encodeURIComponent(ticker)}/forecast`),
      getJson<Factor[]>("/api/factors"),
    ])
      .then(([nextForecast, nextFactors]) => {
        setForecast(nextForecast);
        setFactors(nextFactors);
      })
      .catch(() => setFailed(true));
  }, [ticker]);

  if (failed) return <p className="bad">Factors failed to load. Not verified.</p>;
  return <FactorTable forecast={forecast} factors={factors} />;
}

export function ForecastPanel({ ticker }: { ticker: string }) {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [leans, setLeans] = useState<Leans | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    Promise.all([
      getJson<Forecast | null>(`/api/stocks/${encodeURIComponent(ticker)}/forecast`),
      getJson<Line[]>(`/api/stocks/${encodeURIComponent(ticker)}/story`),
      getJson<Leans | null>(`/api/stocks/${encodeURIComponent(ticker)}/leans`),
    ])
      .then(([nextForecast, nextLines, nextLeans]) => {
        setForecast(nextForecast);
        setLines(nextLines);
        setLeans(nextLeans);
      })
      .catch(() => setFailed(true));
  }, [ticker]);

  if (failed) return <p className="bad">Forecast failed to load. Not verified.</p>;
  return (
    <div>
      <div className={`action ${forecast?.action === "Buy candidate" ? "buy" : ""} ${forecast?.action === "Sell candidate" ? "sell" : ""}`}>
        <small>What to do</small>
        <strong>{forecast?.action ?? "No forecast yet"}</strong>
        <p>
          {forecast
            ? MEANINGS[forecast.action]
            : "Forecasts are written once a day before the US market opens."}
        </p>
      </div>
      <ChecklistPanel ticker={ticker} />
      <PositionPanel ticker={ticker} />
      {leans && <LeanTable leans={leans} />}
      {lines.length > 0 && (
        <>
          <h3>What the data says</h3>
          <Story lines={lines} />
        </>
      )}
      {forecast && (
        <>
          <h3>Tomorrow's forecast ({forecast.target_session})</h3>
          <div className="glance">
            <div>
              <small>Up</small>
              <strong>{percent(forecast.p_up)}</strong>
            </div>
            <div>
              <small>Flat</small>
              <strong>{percent(forecast.p_flat)}</strong>
            </div>
            <div>
              <small>Down</small>
              <strong>{percent(forecast.p_down)}</strong>
            </div>
            <div>
              <small>Likely range (90%)</small>
              <strong>
                {forecast.range_low.toFixed(2)} to {forecast.range_high.toFixed(2)}
              </strong>
            </div>
            <div>
              <small>Options-implied move</small>
              <strong>{NOT_VERIFIED}</strong>
            </div>
            <div>
              <small>Confidence</small>
              <strong>{forecast.next_day_edge ? forecast.confidence : "No reliable edge"}</strong>
            </div>
          </div>
          <small>
            Written {new Date(forecast.created_at).toLocaleString()}, before the outcome, and
            cannot be edited.
          </small>
        </>
      )}
    </div>
  );
}

type Comparison = {
  models: {
    model: string;
    t_stat: number;
    spread: number;
    holdout_spread: number | null;
    worst_year: number | null;
    worst_year_spread: number | null;
    calm_spread: number | null;
    stressed_spread: number | null;
    selected: boolean;
    edge: boolean;
    good: string;
    bad: string;
    caution: string;
  }[];
};

const signed = (value: number | null) =>
  value === null ? NOT_VERIFIED : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;

function ComparisonView({ comparison }: { comparison: Comparison }) {
  return (
    <>
      <h3>Which model type works best?</h3>
      <small>
        Every model faced the same dates. Spread is how much its top-ranked stocks beat its
        bottom-ranked ones over 20 days after costs. Recent years are kept back as a final check.
      </small>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Test score (needs 3.0)</th>
              <th>Spread</th>
              <th>Final check</th>
              <th>Worst year</th>
              <th>Calm markets</th>
              <th>Stressed markets</th>
            </tr>
          </thead>
          <tbody>
            {comparison.models.map((row) => (
              <tr key={row.model}>
                <td>
                  {row.model}
                  {row.selected && " (chosen)"}
                </td>
                <td>{row.t_stat.toFixed(1)}</td>
                <td>{signed(row.spread)}</td>
                <td>{signed(row.holdout_spread)}</td>
                <td>
                  {row.worst_year ?? NOT_VERIFIED} {signed(row.worst_year_spread)}
                </td>
                <td>{signed(row.calm_spread)}</td>
                <td>{signed(row.stressed_spread)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="story">
        {comparison.models.map((row) => (
          <div key={row.model} className={row.edge ? "tone-good" : "tone-neutral"}>
            <strong>{row.model}</strong>
            <span>
              Good: {row.good} Weak: {row.bad} Caution: {row.caution}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

export function IdeasPanel() {
  const [ideas, setIdeas] = useState<Ideas | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    Promise.all([
      getJson<Ideas>("/api/ideas"),
      getJson<Track>("/api/track-record"),
      getJson<Comparison | null>("/api/model-comparison"),
    ])
      .then(([nextIdeas, nextTrack, nextComparison]) => {
        setIdeas(nextIdeas);
        setTrack(nextTrack);
        setComparison(nextComparison);
      })
      .catch(() => setFailed(true));
  }, []);

  if (failed) return <p className="bad">Forecast summary failed to load. Not verified.</p>;
  if (!ideas || !track) return null;
  const list = (items: Ideas["buy"]) =>
    items.length ? items.map((item) => item.ticker).join(", ") : "None";
  return (
    <section>
      <h2>What to do today</h2>
      {!ideas.target_session ? (
        <p>No forecasts yet. They are written once a day before the US market opens.</p>
      ) : ideas.edge ? (
        <div className="glance">
          <div>
            <small>Buy candidates</small>
            <strong className="ok">{list(ideas.buy)}</strong>
          </div>
          <div>
            <small>Sell candidates</small>
            <strong className="bad">{list(ideas.sell)}</strong>
          </div>
        </div>
      ) : (
        <div className="action">
          <strong>No reliable edge</strong>
          <p>
            Testing has not shown the model beats simply holding, so it names no stocks to buy or
            sell.
          </p>
        </div>
      )}
      <h3>Model track record</h3>
      <div className="glance">
        <div>
          <small>Forecasts written</small>
          <strong>{track.written}</strong>
        </div>
        <div>
          <small>Scored so far</small>
          <strong>{track.scored}</strong>
        </div>
        <div>
          <small>Score (lower is better)</small>
          <strong>
            {track.brier === null
              ? NOT_VERIFIED
              : `${track.brier.toFixed(3)} vs ${track.baseline_brier?.toFixed(3)} guessing`}
          </strong>
        </div>
        <div>
          <small>Range hit rate (target 90%)</small>
          <strong>
            {track.range_hit_rate === null ? NOT_VERIFIED : percent(track.range_hit_rate)}
          </strong>
        </div>
        {track.evaluations.map((item) => (
          <div key={item.model}>
            <small>{item.model === "next_day" ? "Next-day test" : "20-day ranking test"}</small>
            <strong>{item.edge ? "Edge" : "No reliable edge"}</strong>
          </div>
        ))}
      </div>
      {comparison && <ComparisonView comparison={comparison} />}
    </section>
  );
}
