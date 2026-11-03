import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";

export type Candle = {
  market_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
};
type Level = { kind: string; price: number; touches: number };
type Signal = {
  name: string;
  label: string;
  direction: string;
  market_date: string;
  detail: string;
  cancellation_level: number;
  sample_size: number;
  win_rate: number | null;
};
export type Chart = {
  stale: boolean;
  signals_blocked: boolean;
  latest_bar: string | null;
  latest_expected_session: string;
  candles: Candle[];
  levels: Level[];
  signals: Signal[];
};

const TIMEFRAMES = ["daily", "weekly", "monthly"];
const COLORS = { up: "#1a8a4f", down: "#c43c3c", a: "#c8872e", b: "#2f7fc1", c: "#8a5cc2" };

function line(candles: Candle[], key: keyof Candle) {
  return candles
    .filter((candle) => candle[key] !== null)
    .map((candle) => ({ time: candle.market_date as Time, value: candle[key] as number }));
}

function theme() {
  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return {
    layout: { background: { color: "transparent" }, textColor: dark ? "#a3a39b" : "#66665f" },
    grid: {
      vertLines: { color: dark ? "#2a2a27" : "#ecece6" },
      horzLines: { color: dark ? "#2a2a27" : "#ecece6" },
    },
    // The same width on both panels keeps their dates lined up.
    rightPriceScale: { minimumWidth: 90 },
    autoSize: true,
  };
}

function Plot({ data }: { data: Chart }) {
  const price = useRef<HTMLDivElement>(null);
  const momentum = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!price.current || !momentum.current) return;
    const charts: IChartApi[] = [createChart(price.current, theme())];
    const main = charts[0];
    const candles = main.addSeries(CandlestickSeries, {
      upColor: COLORS.up,
      downColor: COLORS.down,
      wickUpColor: COLORS.up,
      wickDownColor: COLORS.down,
      borderVisible: false,
    });
    candles.setData(
      data.candles.map((candle) => ({
        time: candle.market_date as Time,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      })),
    );
    const overlays: [keyof Candle, string, string][] = [
      ["sma20", COLORS.a, "20 average"],
      ["sma50", COLORS.b, "50 average"],
      ["sma200", COLORS.c, "200 average"],
    ];
    for (const [key, color, title] of overlays) {
      main
        .addSeries(LineSeries, { color, lineWidth: 1, title, priceLineVisible: false })
        .setData(line(data.candles, key));
    }
    for (const level of data.levels) {
      candles.createPriceLine({
        price: level.price,
        color: level.kind === "resistance" ? COLORS.down : COLORS.up,
        lineStyle: 2,
        lineWidth: 1,
        title: level.kind,
      });
    }
    const volume = main.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      color: "#8a8a82",
    });
    main.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    volume.setData(
      data.candles.map((candle) => ({
        time: candle.market_date as Time,
        value: candle.volume,
      })),
    );

    const lower = createChart(momentum.current, theme());
    charts.push(lower);
    lower
      .addSeries(HistogramSeries, { color: "#8a8a82", title: "MACD histogram" })
      .setData(line(data.candles, "macd_histogram"));
    lower
      .addSeries(LineSeries, { color: COLORS.b, lineWidth: 1, title: "MACD" })
      .setData(line(data.candles, "macd"));
    lower
      .addSeries(LineSeries, { color: COLORS.a, lineWidth: 1, title: "Signal" })
      .setData(line(data.candles, "macd_signal"));
    lower
      .addSeries(LineSeries, {
        color: COLORS.c,
        lineWidth: 1,
        title: "RSI",
        priceScaleId: "rsi",
      })
      .setData(line(data.candles, "rsi"));

    const visible = Math.min(data.candles.length, 180);
    const range = { from: data.candles.length - visible, to: data.candles.length };
    main.timeScale().setVisibleLogicalRange(range);
    main.timeScale().subscribeVisibleLogicalRangeChange((next) => {
      if (next) lower.timeScale().setVisibleLogicalRange(next);
    });
    return () => charts.forEach((chart) => chart.remove());
  }, [data]);

  return (
    <>
      <div className="chart" ref={price} />
      <div className="chart lower" ref={momentum} />
    </>
  );
}

export default function ChartPanel({ ticker }: { ticker: string }) {
  const [timeframe, setTimeframe] = useState("daily");
  const [data, setData] = useState<Chart | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    setData(null);
    setFailed(false);
    fetch(`/api/stocks/${encodeURIComponent(ticker)}/chart?timeframe=${timeframe}`)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then((body) => active && setData(body))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, [ticker, timeframe]);

  return (
    <div>
      <div className="tabs" role="group" aria-label="Timeframe">
        {TIMEFRAMES.map((name) => (
          <button key={name} aria-pressed={name === timeframe} onClick={() => setTimeframe(name)}>
            {name}
          </button>
        ))}
      </div>
      {failed && <p className="bad">Chart failed to load. Data is not verified.</p>}
      {!failed && !data && <p>Loading chart…</p>}
      {data && data.candles.length === 0 && <p>Not verified: no complete prices stored yet.</p>}
      {data && data.candles.length > 0 && (
        <>
          <Plot data={data} />
          <small>
            Prices adjusted for splits and dividends. Top: candles, averages, volume, support and
            resistance. Bottom: MACD and RSI.
          </small>
        </>
      )}
      {data && (
        <>
          <h3>Signals</h3>
          {data.signals_blocked ? (
            <p className="bad">
              Signals blocked: prices are stale. Expected {data.latest_expected_session}, latest is{" "}
              {data.latest_bar ?? "Not verified"}.
            </p>
          ) : data.signals.length === 0 ? (
            <p>Neutral: no rule fired on the latest {timeframe} candle.</p>
          ) : (
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>Label</th>
                    <th>Leans</th>
                    <th>Tested record</th>
                    <th>Sample</th>
                    <th>Cancelled at</th>
                    <th>Rule</th>
                  </tr>
                </thead>
                <tbody>
                  {data.signals.map((signal) => (
                    <tr key={`${signal.name}${signal.direction}`}>
                      <td>{signal.name}</td>
                      <td>{signal.label}</td>
                      <td>{signal.direction}</td>
                      <td>
                        {signal.win_rate === null
                          ? "Not tested yet"
                          : `${(signal.win_rate * 100).toFixed(1)}%`}
                      </td>
                      <td>{signal.sample_size}</td>
                      <td>{signal.cancellation_level.toFixed(2)}</td>
                      <td>{signal.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
