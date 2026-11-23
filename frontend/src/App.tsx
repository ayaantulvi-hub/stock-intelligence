import { useEffect, useState, type ReactNode } from "react";
import { PASSING, type Coverage, type Feed, type Result } from "./api";
import Code from "./Code";
import { explain, type Mode } from "./explain";
import { NOT_VERIFIED } from "./format";
import snippets from "./snippets.json";
import { anyPass, decidingStat, NAMES, STUDIES, useLoad, view, type StudyInfo } from "./studies";

/** A terminal-style layout: a fixed list of screens on the left, one screen at a time on the
 * right, every piece of information in its own labelled panel. */

const SCREENS = ["overview", ...STUDIES.map((s) => s.key), "data"];

function screenFromHash(): string {
  const key = window.location.hash.replace("#", "");
  return SCREENS.includes(key) ? key : "overview";
}

function readMode(): Mode {
  try {
    return localStorage.getItem("explain-mode") === "quant" ? "quant" : "plain";
  } catch {
    return "plain";
  }
}

function Panel({ title, meta, span, children, className = "" }: {
  title: string;
  meta?: ReactNode;
  span: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel span-${span} ${className}`} aria-label={title}>
      <header>
        <h3>{title}</h3>
        {meta && <span className="meta">{meta}</span>}
      </header>
      <div className="body">{children}</div>
    </section>
  );
}

function Mark({ pass }: { pass: boolean | null }) {
  if (pass === null)
    return (
      <span className="mark none" aria-label="not run">
        –
      </span>
    );
  return (
    <span className={`mark ${pass ? "pass" : "fail"}`} aria-label={pass ? "passed" : "failed"}>
      {pass ? "✓" : "✕"}
    </span>
  );
}

function Overview({ data, byStudy, coverage, feeds, go }: {
  data: Result[];
  byStudy: Map<string, Result[]>;
  coverage: Coverage | null;
  feeds: Feed[] | null;
  go: (key: string) => void;
}) {
  const passed = data.filter((r) => PASSING.has(r.verdict)).length;
  const years = data.flatMap((r) => r.period.match(/\d{4}/g)?.map(Number) ?? []);
  const ok = feeds?.filter((f) => f.status === "ok").length;
  return (
    <div className="panels">
      <Panel title="Score" span={8} className="hero" meta={years.length ? `${Math.min(...years)}–${Math.max(...years)}` : NOT_VERIFIED}>
        <h1>
          <span>{data.length} tests.</span> <span className={passed ? "tone-green" : "tone-red"}>{passed} passed.</span>
        </h1>
        <p className="lede">
          Five classic quant ideas, built from scratch and tested the hard way: after costs, on years they never saw, with a
          t-score of 3 to pass.
        </p>
      </Panel>
      <Panel title="Data" span={4} meta={<a href="#data">Details</a>}>
        <dl className="facts">
          <div>
            <dt>Stocks</dt>
            <dd>{coverage ? coverage.stocks.toLocaleString("en-GB") : NOT_VERIFIED}</dd>
          </div>
          <div>
            <dt>Daily price rows</dt>
            <dd>{coverage ? coverage.price_rows.toLocaleString("en-GB") : NOT_VERIFIED}</dd>
          </div>
          <div>
            <dt>Prices up to</dt>
            <dd>{coverage?.last_day ?? NOT_VERIFIED}</dd>
          </div>
          <div>
            <dt>Feeds working</dt>
            <dd className={feeds && ok === feeds.length ? "tone-green" : "tone-amber"}>
              {feeds ? `${ok} of ${feeds.length}` : NOT_VERIFIED}
            </dd>
          </div>
        </dl>
      </Panel>
      <Panel title="Every test" span={12} meta="Click a row to open the study">
        <div className="scroll">
          <table className="board">
            <thead>
              <tr>
                <th scope="col">
                  <span className="sr-only">Result</span>
                </th>
                <th scope="col">Study</th>
                <th scope="col">Version</th>
                <th scope="col">Verdict</th>
                <th scope="col">Deciding statistic</th>
                <th scope="col">Period</th>
              </tr>
            </thead>
            <tbody>
              {STUDIES.flatMap((info) =>
                (byStudy.get(info.key) ?? []).map((r) => {
                  const [label, value] = decidingStat(r);
                  return (
                    <tr key={`${r.study}/${r.variant}`} onClick={() => go(info.key)} className="link-row">
                      <td>
                        <Mark pass={PASSING.has(r.verdict)} />
                      </td>
                      <th scope="row">
                        <a href={`#${info.key}`} onClick={(e) => e.stopPropagation()}>
                          <span className="code-tag">{info.code}</span> {info.title}
                        </a>
                      </th>
                      <td>{NAMES[r.variant] ?? r.variant}</td>
                      <td className={PASSING.has(r.verdict) ? "tone-green" : ""}>{r.verdict}</td>
                      <td className="num">
                        <span className="muted">{label}</span> {value}
                      </td>
                      <td className="num muted">{r.period}</td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel title="What the statistics actually said" span={12}>
        <ul className="findings">
          {STUDIES.map((info) => {
            const rows = byStudy.get(info.key);
            const v = rows ? view(info.key, rows) : null;
            return (
              <li key={info.key}>
                <Mark pass={rows ? anyPass(rows) : null} />
                <span className="code-tag">{info.code}</span>
                <span>{v ? v.finding : `${NOT_VERIFIED}: not run yet.`}</span>
                <span className="meta">{v?.note}</span>
              </li>
            );
          })}
        </ul>
        <p className="closing">Finding a pattern is easy. Testing tells you which ones are real.</p>
      </Panel>
    </div>
  );
}

function Study({ info, rows, mode, setMode }: {
  info: StudyInfo;
  rows: Result[] | undefined;
  mode: Mode;
  setMode: (m: Mode) => void;
}) {
  const snippet = (snippets as Record<string, { file: string; code: string }>)[info.key];
  const v = rows ? view(info.key, rows) : null;
  const words = rows ? explain(info.key, rows) : null;
  return (
    <div className="panels" id={info.key}>
      <Panel title="Study" span={12} className="title" meta={info.tags.join("  ·  ")}>
        <h1>
          <span className="code-tag big">{info.code}</span> {info.title}
        </h1>
        <p className="lede">{info.tagline}</p>
      </Panel>
      {!rows || !v ? (
        <Panel title="Results" span={12}>
          <p className="muted not-run">{NOT_VERIFIED}: this study hasn't run yet.</p>
        </Panel>
      ) : (
        <>
          {v.tiles.map((t) => (
            <Panel key={t.label} title={t.label} span={4} className="tile">
              <strong className={`tone-${t.tone}`}>{t.value}</strong>
            </Panel>
          ))}
          <Panel title="Chart" span={8} meta={v.caption} className="chart-panel">
            {v.chart}
          </Panel>
          <Panel title="Verdicts" span={4}>
            <ul className="verdict-list">
              {rows.map((r) => {
                const [label, value] = decidingStat(r);
                const pass = PASSING.has(r.verdict);
                return (
                  <li key={r.variant}>
                    <Mark pass={pass} />
                    <div>
                      <strong>{NAMES[r.variant] ?? r.variant}</strong>
                      <span className={pass ? "tone-green" : ""}>{r.verdict}</span>
                      <span className="muted num">
                        {label}: {value}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="rule-note">
              {info.key === "value_at_risk"
                ? "To pass: both the Kupiec and Christoffersen tests above p = 0.05."
                : "To pass: t ≥ 3 on the earlier years, and positive on the last two."}
            </p>
          </Panel>
          {words && (
            <Panel
              title="Explanation"
              span={7}
              className={`explain ${mode}`}
              meta={
                <span className="switch" role="radiogroup" aria-label="Explanation level">
                  {(["plain", "quant"] as const).map((m) => (
                    <button key={m} role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
                      {m === "plain" ? "Plain English" : "Quant detail"}
                    </button>
                  ))}
                </span>
              }
            >
              {mode === "plain" ? words.plain : words.quant}
            </Panel>
          )}
        </>
      )}
      {snippet && (
        <Panel title="The code that ran" span={rows && v ? 5 : 12} className="code-panel">
          <Code file={snippet.file} code={snippet.code} />
        </Panel>
      )}
      <Panel title="Sources" span={12} className="sources">
        <p>
          {info.sources.map(([label, url], i) => (
            <span key={url}>
              {i > 0 && "  ·  "}
              <a href={url} target="_blank" rel="noreferrer">
                {label}
              </a>
            </span>
          ))}
        </p>
      </Panel>
    </div>
  );
}

function DataScreen({ coverage, feeds, failed }: { coverage: Coverage | null; feeds: Feed[] | null; failed: boolean }) {
  const tiles: [string, string | null | undefined][] = [
    ["Stocks", coverage?.stocks.toLocaleString("en-GB")],
    ["Daily price rows", coverage?.price_rows.toLocaleString("en-GB")],
    ["First day", coverage?.first_day],
    ["Last day", coverage?.last_day],
  ];
  return (
    <div className="panels" id="data">
      <Panel title="Data" span={12} className="title">
        <h1>What it stands on</h1>
      </Panel>
      {tiles.map(([label, value]) => (
        <Panel key={label} title={label} span={3} className="tile">
          <strong className="tone-plain">{value ?? NOT_VERIFIED}</strong>
        </Panel>
      ))}
      <Panel title="Feeds" span={12}>
        {failed && <p className="muted">{NOT_VERIFIED}: feed status didn't load.</p>}
        {feeds && (
          <div className="scroll">
            <table className="board">
              <thead>
                <tr>
                  <th scope="col">Feed</th>
                  <th scope="col">Source</th>
                  <th scope="col">Last run</th>
                  <th scope="col">State</th>
                </tr>
              </thead>
              <tbody>
                {feeds.map((f) => (
                  <tr key={f.feed}>
                    <th scope="row">{f.feed}</th>
                    <td>{f.source}</td>
                    <td className="num">{f.last_run ? new Date(f.last_run).toLocaleString("en-GB") : "Never"}</td>
                    <td className={f.status === "ok" ? "tone-green" : "tone-amber"}>
                      {f.status === "ok" ? "OK" : `${f.status.replaceAll("_", " ")}${f.message ? `: ${f.message}` : ""}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel title="Limits" span={12}>
        <p className="fine">
          Every test pays 0.10% a trade and 0.5% a year to borrow shares, and needs a t-score of 3 on the earlier years plus a
          positive result on the two held-back years. The stock list is today's companies, so ones that failed are missing and
          results are flattered. Prices come from Tiingo and are not republished. This product uses the FRED® API but is not
          endorsed or certified by the Federal Reserve Bank of St. Louis.
        </p>
      </Panel>
    </div>
  );
}

export default function App() {
  const { data, failed } = useLoad<Result[]>("/api/quant");
  const feeds = useLoad<Feed[]>("/api/feeds");
  const coverage = useLoad<Coverage>("/api/coverage");
  const [screen, setScreen] = useState(screenFromHash);
  const [mode, setModeState] = useState<Mode>(readMode);

  useEffect(() => {
    const onHash = () => setScreen(screenFromHash());
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const i = Number(e.key);
      if (e.key.trim() && Number.isInteger(i) && i >= 0 && i < SCREENS.length) window.location.hash = SCREENS[i];
    };
    window.addEventListener("hashchange", onHash);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const go = (key: string) => {
    window.location.hash = key;
  };
  const setMode = (m: Mode) => {
    setModeState(m);
    try {
      localStorage.setItem("explain-mode", m);
    } catch {
      /* Remembering the choice is a convenience only. */
    }
  };

  const byStudy = new Map<string, Result[]>();
  data?.forEach((r) => byStudy.set(r.study, [...(byStudy.get(r.study) ?? []), r]));
  const passed = data?.filter((r) => PASSING.has(r.verdict)).length ?? 0;
  const lastRun = data?.map((r) => r.run_at).sort().at(-1);
  const info = STUDIES.find((s) => s.key === screen);

  return (
    <div className="terminal">
      <header className="topbar">
        <a className="brand" href="#overview">
          QUANT LAB<span className="dot">.</span>
        </a>
        <span className="status">
          <span className="muted">Tests</span> {data ? `${data.length} · ${passed} passed` : "…"}
        </span>
        <span className="status">
          <span className="muted">Studies run</span> {lastRun ? new Date(lastRun).toLocaleDateString("en-GB") : NOT_VERIFIED}
        </span>
        <span className="status">
          <span className="muted">Prices to</span> {coverage.data?.last_day ?? NOT_VERIFIED}
        </span>
        <span className="status right muted">Research only · places no trades</span>
      </header>
      <nav className="side" aria-label="Screens">
        {SCREENS.map((key, i) => {
          const s = STUDIES.find((x) => x.key === key);
          const rows = byStudy.get(key);
          return (
            <a key={key} href={`#${key}`} className={screen === key ? "on" : ""} aria-current={screen === key ? "page" : undefined}>
              <kbd>{i}</kbd>
              <span className="name">{s ? s.title : key === "overview" ? "Overview" : "Data"}</span>
              {s && data && <Mark pass={rows ? anyPass(rows) : null} />}
            </a>
          );
        })}
        <p className="hint">Press 0–{SCREENS.length - 1} to switch</p>
      </nav>
      <main key={screen}>
        {failed && <p className="error">{NOT_VERIFIED}: the results didn't load. Check that the API is running.</p>}
        {!data && !failed && <p className="muted loading">Loading results…</p>}
        {data && data.length === 0 && screen !== "data" && (
          <p className="muted loading">No study has run yet. Results appear after the weekly run.</p>
        )}
        {data && data.length > 0 && screen === "overview" && (
          <Overview data={data} byStudy={byStudy} coverage={coverage.data} feeds={feeds.data} go={go} />
        )}
        {data && info && <Study info={info} rows={byStudy.get(info.key)} mode={mode} setMode={setMode} />}
        {screen === "data" && <DataScreen coverage={coverage.data} feeds={feeds.data} failed={feeds.failed} />}
      </main>
    </div>
  );
}
