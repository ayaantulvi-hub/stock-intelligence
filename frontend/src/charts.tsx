import { useId, useMemo, useState, type PointerEvent } from "react";
import { monthLabel, num } from "./format";

/** Hand-drawn SVG charts. Every chart has a hover readout and a table view, so no value is
 * reachable only by hovering, and identity is never carried by colour alone. */

const W = 720;
const H = 240;
const PAD = { top: 14, right: 132, bottom: 26, left: 48 };

type Series = { name: string; values: (number | null)[]; role: "s1" | "s2" | "s3" };

function ticks(min: number, max: number, count = 4): number[] {
  const span = max - min || 1;
  const step = 10 ** Math.floor(Math.log10(span / count));
  const nice = [1, 2, 2.5, 5, 10].map((m) => m * step).find((s) => span / s <= count) ?? step * 10;
  const out = [];
  for (let v = Math.ceil(min / nice) * nice; v <= max + 1e-9; v += nice) out.push(Number(v.toFixed(10)));
  return out;
}

function yearTicks(months: string[]): number[] {
  const step = months.length > 120 ? 24 : 12;
  return months
    .map((m, i) => (m.endsWith("-01") && Number(m.slice(0, 4)) % (step / 12) === 0 ? i : -1))
    .filter((i) => i >= 0);
}

function TableView({ caption, months, series, format }: {
  caption: string;
  months: string[];
  series: Series[];
  format: (v: number) => string;
}) {
  return (
    <details className="table-view">
      <summary>Show as a table</summary>
      <div className="scroll">
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>
              <th scope="col">Month</th>
              {series.map((s) => (
                <th scope="col" key={s.name}>
                  {s.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {months.map((m, i) => (
              <tr key={m}>
                <th scope="row">{monthLabel(m)}</th>
                {series.map((s) => (
                  <td key={s.name}>{num(s.values[i]) ? format(s.values[i] as number) : "—"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** One y-scale, 1–2 lines, crosshair readout, end labels, legend. */
export function LineChart({
  title,
  months,
  series,
  format,
  baseline,
  shade,
}: {
  title: string;
  months: string[];
  series: Series[];
  format: (v: number) => string;
  baseline?: number;
  shade?: (number | null)[];
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const values = series.flatMap((s) => s.values).filter(num);
  const min = Math.min(...values, baseline ?? Infinity);
  const max = Math.max(...values, baseline ?? -Infinity);
  const x = (i: number) => PAD.left + (i / Math.max(1, months.length - 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - min) / (max - min || 1)) * (H - PAD.top - PAD.bottom);
  const paths = useMemo(
    () =>
      series.map((s) =>
        s.values
          .map((v, i) => (num(v) ? `${i === 0 || !num(s.values[i - 1]) ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}` : ""))
          .join(""),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [series, min, max, months.length],
  );
  if (!months.length || !values.length) return <p className="muted">Not verified: no stored series.</p>;
  const move = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.left) / (W - PAD.left - PAD.right)) * (months.length - 1));
    setHover(Math.max(0, Math.min(months.length - 1, i)));
  };
  const last = months.length - 1;
  return (
    <figure className="chart">
      <figcaption id={id}>{title}</figcaption>
      {series.length > 1 && (
        <ul className="legend" aria-hidden="true">
          {series.map((s) => (
            <li key={s.name}>
              <span className={`key line ${s.role}`} />
              {s.name}
            </li>
          ))}
        </ul>
      )}
      <div className="plot">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-labelledby={id}
          onPointerMove={move}
          onPointerLeave={() => setHover(null)}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight") setHover((h) => Math.min(last, (h ?? -1) + 1));
            if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? last + 1) - 1));
          }}
          onBlur={() => setHover(null)}
        >
          {shade?.map((s, i) =>
            num(s) && s > 0 ? (
              <rect
                key={i}
                className="shade"
                x={x(i) - (W - PAD.left - PAD.right) / months.length / 2}
                y={PAD.top}
                width={(W - PAD.left - PAD.right) / months.length}
                height={H - PAD.top - PAD.bottom}
                opacity={0.08 + 0.22 * s}
              />
            ) : null,
          )}
          {ticks(min, max).map((t) => (
            <g key={t} className="grid">
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                {format(t)}
              </text>
            </g>
          ))}
          {baseline !== undefined && (
            <line className="zero" x1={PAD.left} x2={W - PAD.right} y1={y(baseline)} y2={y(baseline)} />
          )}
          {yearTicks(months).map((i) => (
            <text key={i} className="axis" x={x(i)} y={H - 6} textAnchor="middle">
              {months[i].slice(0, 4)}
            </text>
          ))}
          {series.map((s, k) => (
            <path key={s.name} d={paths[k]} className={`series ${s.role}`} />
          ))}
          {series.map((s) =>
            num(s.values[last]) ? (
              <text key={s.name} className="end-label" x={x(last) + 8} y={y(s.values[last] as number)} dy="0.32em">
                {series.length > 1 ? `${s.name} ` : ""}
                {format(s.values[last] as number)}
              </text>
            ) : null,
          )}
          {hover !== null && (
            <g className="crosshair">
              <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} />
              {series.map((s) =>
                num(s.values[hover]) ? (
                  <circle key={s.name} className={`dot ${s.role}`} cx={x(hover)} cy={y(s.values[hover] as number)} r={4} />
                ) : null,
              )}
            </g>
          )}
        </svg>
        {hover !== null && (
          <div className="tooltip" style={{ left: `${(x(hover) / W) * 100}%` }} role="status">
            <div className="tip-date">{monthLabel(months[hover])}</div>
            {series.map((s) => (
              <div key={s.name} className="tip-row">
                <span className={`key line ${s.role}`} />
                <strong>{num(s.values[hover]) ? format(s.values[hover] as number) : "—"}</strong>
                <span>{s.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <TableView caption={title} months={months} series={series} format={format} />
    </figure>
  );
}

/** Monthly counts as thin bars rising from zero: one small chart per model, same scale. */
export function BarStrip({
  title,
  months,
  values,
  max,
}: {
  title: string;
  months: string[];
  values: number[];
  max: number;
}) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const h = 64;
  const w = W - PAD.left - PAD.right;
  const bw = w / months.length;
  return (
    <figure className="chart strip">
      <figcaption id={id}>{title}</figcaption>
      <div className="plot">
        <svg viewBox={`0 0 ${W} ${h + 18}`} role="img" aria-labelledby={id} onPointerLeave={() => setHover(null)}>
          <line className="zero" x1={PAD.left} x2={PAD.left + w} y1={h} y2={h} />
          {values.map((v, i) => (
            <g key={months[i]} onPointerEnter={() => setHover(i)}>
              <rect className="hit" x={PAD.left + i * bw} y={0} width={bw} height={h} />
              {v > 0 && (
                <rect
                  className={`bar ${hover === i ? "lift" : ""}`}
                  x={PAD.left + i * bw + Math.min(1, bw * 0.15)}
                  y={h - (v / max) * (h - 4)}
                  width={Math.max(1, bw - Math.min(2, bw * 0.3))}
                  height={(v / max) * (h - 4)}
                  rx={Math.min(2, bw / 3)}
                />
              )}
            </g>
          ))}
          {yearTicks(months).map((i) => (
            <text key={i} className="axis" x={PAD.left + i * bw} y={h + 14} textAnchor="middle">
              {months[i].slice(0, 4)}
            </text>
          ))}
        </svg>
        {hover !== null && (
          <div className="tooltip" style={{ left: `${((PAD.left + (hover + 0.5) * bw) / W) * 100}%` }} role="status">
            <div className="tip-date">{monthLabel(months[hover])}</div>
            <div className="tip-row">
              <strong>{values[hover]}</strong>
              <span>{values[hover] === 1 ? "breach" : "breaches"}</span>
            </div>
          </div>
        )}
      </div>
    </figure>
  );
}

export { TableView };
