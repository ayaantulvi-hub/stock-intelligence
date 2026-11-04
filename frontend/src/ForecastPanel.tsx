import { useCallback, useEffect, useState } from "react";
import ChecklistPanel, { HowMuch } from "./ChecklistPanel";
import PositionPanel from "./PositionPanel";
import { leanRow } from "./leanRow";

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
  top: Pick[];
  bottom: Pick[];
};
type Pick = { ticker: string; name: string; rank: number; price: number; reasons: string[] };

function PickList({ title, picks, tone, onOpen }: {
  title: string;
  picks: Pick[];
  tone: string;
  onOpen?: (ticker: string) => void;
}) {
  return (
    <div className="picks">
      <h3 className={tone}>{title}</h3>
      <ol>
        {picks.map((pick) => (
          <li key={pick.ticker}>
            <button className="link" onClick={() => onOpen?.(pick.ticker)}>
              {pick.ticker}
            </button>{" "}
            {pick.name}, upside rank {Math.round(pick.rank * 100)}
            <small>
              {pick.reasons.length ? `Why: ${pick.reasons.join(", ")}` : "No single factor stands out"}
            </small>
          </li>
        ))}
      </ol>
    </div>
  );
}
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
  meaning: string;
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

function Tug({ leans }: { leans: Leans }) {
  const side = (lean: string) => leans.factors.filter((row) => row.lean === lean);
  const blocks = (rows: Lean[]) =>
    rows.map((row) => (
      <span
        key={row.factor}
        title={`${row.name}: ${row.evidence}`}
        className={`tug-block ${row.proven ? "proven" : ""}`}
      />
    ));
  const sell = side("Sell");
  const buy = side("Buy");
  const model = leans.overall.lean;
  const disagrees =
    (model === "Buy" && sell.length > buy.length) || (model === "Sell" && buy.length > sell.length);
  return (
    <div className="tug">
      <h3>What each factor says on its own</h3>
      <div className="tug-labels">
        <span>{sell.length} lean sell</span>
        <span>{buy.length} lean buy</span>
      </div>
      <div className="tug-row">
        <div className="tug-side sell">{blocks(sell)}</div>
        <div className="tug-axis" />
        <div className="tug-side buy">{blocks(buy)}</div>
      </div>
      <small>
        Each block is one factor taken alone. Solid passed testing here. Outlined is only backed by
        a paper.
      </small>
      {disagrees && (
        <p className="lean">
          Why this differs from the answer at the top: the model leans {model} because it looks at
          how factors combine and learns which matter, so it doesn't count these blocks. Disagreement
          like this is a reason to be more careful.
        </p>
      )}
    </div>
  );
}

function LeanTable({ leans }: { leans: Leans }) {
  return (
    <>
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
          <strong className="ok">{leans.paper_buy}</strong>
        </div>
        <div>
          <small>Unproven, lean sell</small>
          <strong className="bad">{leans.paper_sell}</strong>
        </div>
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
              <th>What it means</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {leans.factors.map((row) => (
              <tr key={row.factor} className={leanRow(row.lean)}>
                <td>{row.name}</td>
                <td>
                  {row.percentile}
                  <span className="meter">
                    <i style={{ left: `calc(${row.percentile}% - 2px)` }} />
                  </span>
                </td>
                <td className={row.lean === "Buy" ? "ok" : row.lean === "Sell" ? "bad" : ""}>
                  {row.lean}
                </td>
                <td className="wrap">{row.meaning}</td>
                <td className="wrap">{row.evidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

type Decision = {
  call: string;
  reason: string;
  proven: boolean;
  kind: string;
  owned: boolean;
  reasons_for: string[];
  reasons_against: string[];
  next_step: string;
};

type Line = {
  topic: string;
  tone: string;
  text: string;
  why: string;
  meaning: string;
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
          <p className="so-what">
            <b>What this means for you:</b> {line.meaning}
          </p>
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

type FiledEvent = {
  date: string;
  url: string;
  source: string;
  events: { item: string; meaning: string; serious: boolean }[];
};

function CompanyEvents({ ticker }: { ticker: string }) {
  const [rows, setRows] = useState<FiledEvent[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    getJson<FiledEvent[]>(`/api/stocks/${encodeURIComponent(ticker)}/events`)
      .then(setRows)
      .catch(() => setFailed(true));
  }, [ticker]);
  const serious = rows?.some((row) => row.events.some((item) => item.serious)) ?? false;
  return (
    <details className="fold">
      <summary>
        What the company reported {serious && <span className="bad">(something serious)</span>}
      </summary>
      <small>
        Big events a US company must report to the regulator within days. This shows the type of
        event. Open the filing for the detail.
      </small>
      {failed && <p className="bad">Could not load company events. Refresh to try again.</p>}
      {rows?.length === 0 && <p>No events are stored for the last 180 days.</p>}
      <ul>
        {rows?.map((row) => (
          <li key={row.url}>
            {row.date}:{" "}
            {row.events.map((item) => (
              <span key={item.item} className={item.serious ? "bad" : ""}>
                {item.meaning}.{" "}
              </span>
            ))}
            <a href={row.url} target="_blank" rel="noreferrer">
              Filing ({row.source})
            </a>
          </li>
        ))}
      </ul>
    </details>
  );
}

type TradeView = {
  call: string;
  reason: string;
  kind: string;
  proven: boolean;
  hold: number | null;
  stop: number | null;
  target: number | null;
  patterns: {
    id: string;
    name: string;
    direction: string;
    meaning: string;
    proven: boolean;
    failed: boolean;
    signals: number | null;
    win_rate: number | null;
    cancel: number;
  }[];
};
type InvestView = { call: string; reason: string; kind: string; hold: string | null };

function Horizons({ ticker }: { ticker: string }) {
  const [views, setViews] = useState<{ trade: TradeView; invest: InvestView } | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    getJson<{ trade: TradeView; invest: InvestView }>(
      `/api/stocks/${encodeURIComponent(ticker)}/horizons`,
    )
      .then(setViews)
      .catch(() => setFailed(true));
  }, [ticker]);
  if (failed) return <p className="bad">Could not load the two answers. Refresh to try again.</p>;
  if (!views?.trade) return null;
  const { trade, invest } = views;
  return (
    <div className="horizons">
      <section className={`horizon ${trade.kind}`}>
        <small>Short-term trade, 1 to 5 days</small>
        <h4>{trade.call}</h4>
        <p>{trade.reason}</p>
        {trade.hold && <p><b>How long:</b> sell within {trade.hold} trading days, or at the stop or target.</p>}
        {!trade.proven && trade.kind !== "neutral" && <p>Unproven, so treat it as a guess.</p>}
        {trade.patterns.map((item) => (
          <p key={item.id}>
            <span className={item.direction === "bullish" ? "ok" : item.direction === "bearish" ? "bad" : ""}>
              {item.name}
            </span>
            : {item.meaning}{" "}
            {item.signals === null
              ? "Not tested yet."
              : `Tested on ${item.signals.toLocaleString()} past cases: ${Math.round((item.win_rate ?? 0) * 100)}% made money.`}{" "}
            Cancelled at {item.cancel.toFixed(2)}.
          </p>
        ))}
        {trade.kind === "buy" && trade.stop !== null && trade.target !== null && (
          <HowMuch ticker={ticker} keep="Week" stop={trade.stop} target={trade.target} />
        )}
        <small>Uses daily candles, so it can't time moves within a day.</small>
      </section>
      <section className={`horizon ${invest.kind}`}>
        <small>Long-term investment, months to years</small>
        <h4>{invest.call}</h4>
        <p>{invest.reason}</p>
        {invest.hold && <p><b>How long:</b> {invest.hold}</p>}
        <small>Company checks only, not proven in this app.</small>
      </section>
    </div>
  );
}

type Listed = { ticker: string; name: string; call: string; reason: string; kind: string };

function ListTable({ url, onOpen, empty }: {
  url: string;
  onOpen: (ticker: string) => void;
  empty: string;
}) {
  const [rows, setRows] = useState<Listed[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    getJson<Listed[]>(url)
      .then(setRows)
      .catch(() => setFailed(true));
  }, [url]);
  if (failed) return <p className="bad">Could not load this list. Refresh to try again.</p>;
  if (!rows) return <p>Loading…</p>;
  if (rows.length === 0) return <p>{empty}</p>;
  return (
    <div className="scroll">
      <table>
        <tbody>
          {rows.map((row) => (
            <tr key={row.ticker} className={row.kind === "buy" ? "row-buy" : "row-sell"}>
              <td>
                <button className="link" onClick={() => onOpen(row.ticker)}>
                  {row.ticker}
                </button>
              </td>
              <td>{row.call}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TradesPanel({ onOpen }: { onOpen: (ticker: string) => void }) {
  return (
    <>
      <p className="plain">
        <b>Sell within 5 trading days, or sooner at the stop or target.</b> Tap a stock for its
        exact prices. Unproven until the weekly test, so treat these as guesses.
      </p>
      <ListTable url="/api/trades" onOpen={onOpen} empty="No candle signals today. Do nothing." />
    </>
  );
}

export function InvestPanel({ onOpen }: { onOpen: (ticker: string) => void }) {
  return (
    <>
      <p className="plain">
        <b>Buy and keep for years while the company checks hold.</b> Review after each yearly
        report. These rules aren't proven in this app.
      </p>
      <ListTable
        url="/api/investments"
        onOpen={onOpen}
        empty="No stock passes the company checks yet. More appear as data loads."
      />
    </>
  );
}

type Lens = { name: string; source: string; verdict: string; reason: string; teaches: string };
type Trap = { name: string; source: string; text: string };
type Review = { lenses: Lens[]; agree: number; against: number; unknown: number; traps: Trap[] };
const VERDICTS: Record<string, [string, string]> = {
  good: ["Yes", "ok"],
  bad: ["No", "bad"],
  mixed: ["Mixed", ""],
  unknown: ["Not verified", ""],
};

function ExpertReview({ ticker }: { ticker: string }) {
  const [review, setReview] = useState<Review | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    getJson<Review>(`/api/stocks/${encodeURIComponent(ticker)}/experts`)
      .then(setReview)
      .catch(() => setFailed(true));
  }, [ticker]);
  if (failed) return <p className="bad">Could not load the expert review. Refresh to try again.</p>;
  if (!review?.lenses) return null;
  return (
    <>
      {review.traps.length > 0 && (
        <div className="traps">
          <h4>Before you decide</h4>
          <ul>
            {review.traps.map((trap) => (
              <li key={trap.name}>
                <b>{trap.name}.</b> {trap.text} <small>{trap.source}</small>
              </li>
            ))}
          </ul>
        </div>
      )}
      <details className="fold">
        <summary>
          Expert review: {review.agree} in favour, {review.against} against
        </summary>
        <small>
          Published investing methods run as fixed rules on this company's real figures. They are
          not the opinion of any named investor. Most are not proven in this app.
        </small>
        <div className="scroll">
          <table>
            <tbody>
              {review.lenses.map((lens) => {
                const [word, tone] = VERDICTS[lens.verdict];
                return (
                  <tr key={lens.name} className={leanRow(lens.verdict)}>
                    <td>{lens.name}</td>
                    <td className={tone}>{word}</td>
                    <td>
                      {lens.reason}
                      <small>
                        {lens.teaches} {lens.source}.
                      </small>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

export function ForecastPanel({ ticker }: { ticker: string }) {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [leans, setLeans] = useState<Leans | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [problems, setProblems] = useState<string[]>([]);

  const loadDecision = useCallback(() => {
    getJson<Decision>(`/api/stocks/${encodeURIComponent(ticker)}/decision`)
      .then(setDecision)
      .catch(() => setProblems((list) => [...list, "the buy or sell answer"]));
  }, [ticker]);

  useEffect(loadDecision, [loadDecision]);

  useEffect(() => {
    // Each part loads alone, so one failure can't hide the rest of the page.
    const base = `/api/stocks/${encodeURIComponent(ticker)}`;
    const note = (part: string) => () => setProblems((list) => [...list, part]);
    setProblems([]);
    getJson<Forecast | null>(`${base}/forecast`).then(setForecast).catch(note("the forecast"));
    getJson<Line[]>(`${base}/story`).then(setLines).catch(note("the data summary"));
    getJson<Leans | null>(`${base}/leans`).then(setLeans).catch(note("the factor table"));
  }, [ticker]);

  const tone = decision?.kind === "neutral" ? "" : (decision?.kind ?? "");
  return (
    <div>
      {problems.length > 0 && (
        <p className="bad">Could not load {problems.join(", ")}. Refresh to try again.</p>
      )}
      <div className="verdict">
        <h3 className={tone}>{decision?.call ?? "Checking…"}</h3>
        {decision && (
          <>
            <p>
              {decision.reason}
              {!decision.proven && decision.kind !== "neutral" && " Unproven, so treat it as a guess."}
            </p>
            <div className="why">
              <div>
                <h4 className="ok">In its favour</h4>
                <ul className="ok">
                  {decision.reasons_for.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                  {decision.reasons_for.length === 0 && <li>Nothing stands out.</li>}
                </ul>
              </div>
              <div>
                <h4 className="bad">Reasons for caution</h4>
                <ul className="bad">
                  {decision.reasons_against.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                  {decision.reasons_against.length === 0 && <li>Nothing stands out.</li>}
                </ul>
              </div>
            </div>
            <p className="step">
              <b>Your next step:</b> {decision.next_step}
            </p>
            {!decision.owned && ["Buy", "Leans buy"].includes(decision.call) && (
              <HowMuch ticker={ticker} />
            )}
          </>
        )}
      </div>
      <Horizons ticker={ticker} />
      <CompanyEvents ticker={ticker} />
      <ExpertReview ticker={ticker} />
      <details className="fold">
        <summary>{decision?.owned ? "Your position" : "I own this stock"}</summary>
        <PositionPanel ticker={ticker} onChange={loadDecision} />
      </details>
      <details className="fold">
        <summary>See the full detail</summary>
      {leans && <Tug leans={leans} />}
      {forecast && (
        <>
          <h3>Chances for {forecast.target_session}</h3>
          <div className="odds" role="img" aria-label={`Down ${percent(forecast.p_down)}, flat ${percent(forecast.p_flat)}, up ${percent(forecast.p_up)}`}>
            <span className="down" style={{ flexGrow: forecast.p_down, flexBasis: 0 }}>
              Down {percent(forecast.p_down)}
            </span>
            <span className="flat" style={{ flexGrow: forecast.p_flat, flexBasis: 0 }}>
              {forecast.p_flat >= 0.12 ? `Flat ${percent(forecast.p_flat)}` : ""}
            </span>
            <span className="up" style={{ flexGrow: forecast.p_up, flexBasis: 0 }}>
              Up {percent(forecast.p_up)}
            </span>
          </div>
          <div className="glance">
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
            Written {new Date(forecast.created_at).toLocaleString()}, before the outcome. It can't
            be edited.
          </small>
        </>
      )}
      {lines.length > 0 && (
        <>
          <h3>What the data says</h3>
          <Story lines={lines} />
        </>
      )}
      {leans && (
        <details className="fold">
          <summary>Every factor, and which way it leans</summary>
          <LeanTable leans={leans} />
        </details>
      )}
      <details className="fold">
        <summary>Before you trade: checklist, exit prices and how much to buy</summary>
        <ChecklistPanel ticker={ticker} />
      </details>
      </details>
    </div>
  );
}
type Comparison = {
  weights?: { factor: string; name: string; weight: number }[];
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
      {comparison.weights && comparison.weights.length > 0 && (
        <>
          <h3>Which factors count most</h3>
          <small>
            How much the model relied on each factor, learned from past data. Counting most doesn't
            prove a factor works, and the stock list's bias may affect this.
          </small>
          <ul className="weights">
            {comparison.weights.map((row) => (
              <li key={row.factor}>
                <span>{row.name}</span>
                <span className="meter wide">
                  <b style={{ width: `${(row.weight / comparison.weights![0].weight) * 100}%` }} />
                </span>
                <span>{(row.weight * 100).toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </>
      )}
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

export function IdeasPanel({
  part = "today",
  onOpen,
}: {
  part?: "today" | "record";
  onOpen?: (ticker: string) => void;
}) {
  const [ideas, setIdeas] = useState<Ideas | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // Each part loads alone, so a problem with one can't hide the buy and sell lists.
    getJson<Ideas>("/api/ideas")
      .then(setIdeas)
      .catch(() => setFailed(true));
    getJson<Track>("/api/track-record")
      .then(setTrack)
      .catch(() => setTrack(null));
    getJson<Comparison | null>("/api/model-comparison")
      .then(setComparison)
      .catch(() => setComparison(null));
  }, []);

  if (failed) return <p className="bad">Forecast summary failed to load. Not verified.</p>;
  if (!ideas) return null;
  const list = (items: Ideas["buy"]) =>
    items.length ? items.map((item) => item.ticker).join(", ") : "None";
  return (
    <section>
      {part === "today" ? (
        <>
      <h2>What to buy and sell today</h2>
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
        <>
          <div className="action">
            <strong>Unproven picks: use with care</strong>
            <p>
              The model hasn't passed testing yet (no reliable edge), so these are its best guesses,
              not recommendations. Use them as a list to research or try in your simulator.
            </p>
          </div>
          <div className="pick-grid">
            <PickList title="Biggest upside, best first" picks={ideas.top} tone="ok" onOpen={onOpen} />
            <PickList title="Weakest, worst first" picks={ideas.bottom} tone="bad" onOpen={onOpen} />
          </div>
          <small>
            A sell lean means avoid or review it if you own it. Ranked for the next 20 days.
          </small>
        </>
      )}
        </>
      ) : track ? (
        <>
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
        </>
      ) : null}
    </section>
  );
}
