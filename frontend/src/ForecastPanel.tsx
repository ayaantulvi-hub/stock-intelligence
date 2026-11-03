import { useEffect, useState } from "react";

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

export function ForecastPanel({ ticker }: { ticker: string }) {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [factors, setFactors] = useState<Factor[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
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
      {forecast && (
        <>
          <h3>Forecast for {forecast.target_session}</h3>
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
      <FactorTable forecast={forecast} factors={factors} />
    </div>
  );
}

export function IdeasPanel() {
  const [ideas, setIdeas] = useState<Ideas | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    Promise.all([getJson<Ideas>("/api/ideas"), getJson<Track>("/api/track-record")])
      .then(([nextIdeas, nextTrack]) => {
        setIdeas(nextIdeas);
        setTrack(nextTrack);
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
    </section>
  );
}
