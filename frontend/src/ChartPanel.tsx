import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  LineStyle,
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
  baseline_win_rate: number | null;
};
type Summary = {
  close: number;
  change_percent: number | null;
  above_50: boolean | null;
  above_200: boolean | null;
  rsi: number | null;
  rsi_state: string | null;
  percent_to_resistance: number | null;
  percent_to_support: number | null;
};
export type Chart = {
  summary: Summary | null;
  stale: boolean;
  signals_blocked: boolean;
  latest_bar: string | null;
  latest_expected_session: string;
  candles: Candle[];
  levels: Level[];
  fibonacci?: { levels: { ratio: number; price: number }[] } | null;
  signals: Signal[];
};

const TIMEFRAMES = ["daily", "weekly", "monthly"];
const RANGES: [string, number][] = [
  ["3M", 3],
  ["6M", 6],
  ["1Y", 12],
  ["5Y", 60],
  ["All", 0],
];
const NOT_VERIFIED = "Not verified";
const COLORS = { up: "#1a8a4f", down: "#c43c3c", a: "#c8872e", b: "#2f7fc1", c: "#8a5cc2" };

// Blank warm-up bars stay in as empty points, so every panel keeps the same dates.
function line(candles: Candle[], key: keyof Candle) {
  return candles.map((candle) => {
    const time = candle.market_date as Time;
    return candle[key] === null ? { time } : { time, value: candle[key] as number };
  });
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

function startIndex(candles: Candle[], months: number) {
  if (!months || candles.length === 0) return 0;
  const start = new Date(candles[candles.length - 1].market_date);
  start.setMonth(start.getMonth() - months);
  const day = start.toISOString().slice(0, 10);
  const index = candles.findIndex((candle) => candle.market_date >= day);
  return index < 0 ? 0 : index;
}

function Plot({ data, months }: { data: Chart; months: number }) {
  const price = useRef<HTMLDivElement>(null);
  const macdPanel = useRef<HTMLDivElement>(null);
  const rsiPanel = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<Candle | null>(null);
  const shown = hovered ?? data.candles[data.candles.length - 1];

  useEffect(() => {
    if (!price.current || !macdPanel.current || !rsiPanel.current) return;
    const main = createChart(price.current, theme());
    const macdChart = createChart(macdPanel.current, theme());
    const rsiChart = createChart(rsiPanel.current, theme());
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
    const overlays: [keyof Candle, string][] = [
      ["sma20", COLORS.a],
      ["sma50", COLORS.b],
      ["sma200", COLORS.c],
    ];
    for (const [key, color] of overlays) {
      main
        .addSeries(LineSeries, {
          color,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        })
        .setData(line(data.candles, key));
    }
    for (const item of data.fibonacci?.levels ?? []) {
      candles.createPriceLine({
        price: item.price,
        color: "#94640f",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: `Fib ${(item.ratio * 100).toFixed(1)}%`,
      });
    }
    for (const level of data.levels) {
      candles.createPriceLine({
        price: level.price,
        color: level.kind === "resistance" ? COLORS.down : COLORS.up,
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        title: level.kind,
      });
    }
    const volume = main.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    main.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    volume.setData(
      data.candles.map((candle) => ({
        time: candle.market_date as Time,
        value: candle.volume,
        color: candle.close >= candle.open ? `${COLORS.up}66` : `${COLORS.down}66`,
      })),
    );

    macdChart
      .addSeries(HistogramSeries, { lastValueVisible: false, priceLineVisible: false })
      .setData(
        line(data.candles, "macd_histogram").map((point) =>
          "value" in point
            ? {
                ...point,
                color: (point.value as number) >= 0 ? `${COLORS.up}99` : `${COLORS.down}99`,
              }
            : point,
        ),
      );
    macdChart
      .addSeries(LineSeries, {
        color: COLORS.b,
        lineWidth: 2,
        lastValueVisible: false,
        priceLineVisible: false,
      })
      .setData(line(data.candles, "macd"));
    macdChart
      .addSeries(LineSeries, {
        color: COLORS.a,
        lineWidth: 2,
        lastValueVisible: false,
        priceLineVisible: false,
      })
      .setData(line(data.candles, "macd_signal"));

    const rsi = rsiChart.addSeries(LineSeries, {
      color: COLORS.c,
      lineWidth: 2,
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
      priceLineVisible: false,
    });
    rsi.setData(line(data.candles, "rsi"));
    for (const [level, color] of [
      [70, COLORS.down],
      [30, COLORS.up],
    ] as [number, string][]) {
      rsi.createPriceLine({
        price: level,
        color,
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
      });
    }

    const byDate = new Map(data.candles.map((candle) => [candle.market_date, candle]));
    main.subscribeCrosshairMove((event) => {
      setHovered(event.time ? (byDate.get(String(event.time)) ?? null) : null);
    });

    const range = {
      from: startIndex(data.candles, months),
      to: data.candles.length + 2,
    };
    const panels = [main, macdChart, rsiChart];
    panels.forEach((chart) => chart.timeScale().setVisibleLogicalRange(range));
    // Moving any panel moves the others, so all three always show the same dates.
    const followers: IChartApi[][] = panels.map((chart) => panels.filter((p) => p !== chart));
    panels.forEach((chart, index) => {
      chart.timeScale().subscribeVisibleLogicalRangeChange((next) => {
        if (next) followers[index].forEach((p) => p.timeScale().setVisibleLogicalRange(next));
      });
    });
    return () => panels.forEach((chart) => chart.remove());
  }, [data, months]);

  return (
    <>
      <div className="readout">
        <strong>{shown.market_date}</strong>
        <span>Open {shown.open.toFixed(2)}</span>
        <span>High {shown.high.toFixed(2)}</span>
        <span>Low {shown.low.toFixed(2)}</span>
        <span>Close {shown.close.toFixed(2)}</span>
        <span>Volume {Math.round(shown.volume).toLocaleString()}</span>
      </div>
      <div className="key">
        <span style={{ color: COLORS.a }}>━ 20 average</span>
        <span style={{ color: COLORS.b }}>━ 50 average</span>
        <span style={{ color: COLORS.c }}>━ 200 average</span>
        <span className="ok">┅ support</span>
        <span className="bad">┅ resistance</span>
      </div>
      <div className="chart" ref={price} />
      <h4>
        MACD <span style={{ color: COLORS.b }}>━ line</span>{" "}
        <span style={{ color: COLORS.a }}>━ signal</span>
      </h4>
      <div className="chart lower" ref={macdPanel} />
      <h4>RSI (above 70 overbought, below 30 oversold)</h4>
      <div className="chart lower" ref={rsiPanel} />
    </>
  );
}

function yesNo(value: boolean | null, yes: string, no: string) {
  return value === null ? NOT_VERIFIED : value ? yes : no;
}

function percent(value: number | null) {
  return value === null ? NOT_VERIFIED : `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function Glance({ summary }: { summary: Summary }) {
  const tone = (good: boolean | null) => (good === null ? "" : good ? "ok" : "bad");
  const cards: [string, string, string][] = [
    ["Last close", summary.close.toFixed(2), ""],
    [
      "Change",
      percent(summary.change_percent),
      tone(summary.change_percent === null ? null : summary.change_percent >= 0),
    ],
    ["50 average", yesNo(summary.above_50, "Price above", "Price below"), tone(summary.above_50)],
    [
      "200 average",
      yesNo(summary.above_200, "Price above", "Price below"),
      tone(summary.above_200),
    ],
    [
      "RSI",
      summary.rsi === null ? NOT_VERIFIED : `${summary.rsi.toFixed(0)}, ${summary.rsi_state}`,
      "",
    ],
    ["To resistance", percent(summary.percent_to_resistance), ""],
    ["To support", percent(summary.percent_to_support), ""],
  ];
  return (
    <div className="glance">
      {cards.map(([name, value, className]) => (
        <div key={name}>
          <small>{name}</small>
          <strong className={className}>{value}</strong>
        </div>
      ))}
    </div>
  );
}

export default function ChartPanel({ ticker }: { ticker: string }) {
  const [timeframe, setTimeframe] = useState("daily");
  const [months, setMonths] = useState(12);
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
        <span className="spacer" />
        {RANGES.map(([name, value]) => (
          <button key={name} aria-pressed={value === months} onClick={() => setMonths(value)}>
            {name}
          </button>
        ))}
      </div>
      {failed && <p className="bad">Chart failed to load. Data is not verified.</p>}
      {!failed && !data && <p>Loading chart…</p>}
      {data && data.candles.length === 0 && <p>Not verified: no complete prices stored yet.</p>}
      {data && data.candles.length > 0 && (
        <>
          {data.summary && <Glance summary={data.summary} />}
          <Plot data={data} months={months} />
          <small>Prices adjusted for splits and dividends. These are facts, not predictions.</small>
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
                      <td>{signal.label === "Neutral" ? "No reliable edge" : signal.label}</td>
                      <td>{signal.direction}</td>
                      <td>
                        {signal.win_rate === null
                          ? "Not tested yet"
                          : `${(signal.win_rate * 100).toFixed(1)}% vs ${(
                              (signal.baseline_win_rate ?? 0) * 100
                            ).toFixed(1)}% baseline`}
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
