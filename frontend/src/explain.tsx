import type { ReactNode } from "react";
import { PASSING, type Result, type Summary } from "./api";
import { fixed, num, pct } from "./format";
import { averageNet } from "./studies";

/** Two readings of every study: plain English for anyone, and the full method for a quant.
 * Every number comes from the stored result. Sentences that depend on a result are picked by
 * the verdict or by comparing stored figures, never written in as a result. */

export type Mode = "plain" | "quant";
type Both = { plain: ReactNode; quant: ReactNode };

const find = (rows: Result[], variant: string) => rows.find((r) => r.variant === variant);
const s = (r?: Result) => r?.metrics.strategy as Summary | undefined;
const b = (r?: Result) => r?.metrics.baseline as Summary | undefined;
const pass = (r?: Result) => (r ? PASSING.has(r.verdict) : false);
const m = (r: Result | undefined, key: string) => r?.metrics[key];
const lower = (a: unknown, c: unknown) => num(a) && num(c) && a < c;

function Table({ head, rows }: { head: string[]; rows: (string | ReactNode)[][] }) {
  return (
    <div className="scroll">
      <table className="stats">
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, k) => (k === 0 ? <th key={k} scope="row">{cell}</th> : <td key={k}>{cell}</td>))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function valueAtRisk(rows: Result[]): Both {
  const models = [
    ["Historical", find(rows, "historical")],
    ["Normal", find(rows, "normal")],
    ["EWMA", find(rows, "ewma")],
  ] as const;
  const failed = models.filter(([, r]) => r && !pass(r));
  const passed = models.filter(([, r]) => r && pass(r));
  const days = m(models[2][1], "days");
  return {
    plain: (
      <>
        <p>
          Value at Risk answers one question: on a bad day, how much could we lose? We set the line so that a worse
          loss should happen on about 1 day in 20. Then we checked each model against{" "}
          {num(days) ? `${days.toLocaleString("en-GB")} real days` : "every real day"}.
        </p>
        <p>
          Getting the count right isn't enough. If the bad days arrive in bunches, the model is calm exactly when
          danger is highest.
        </p>
        {failed.map(([n, r]) => (
          <p key={n}>
            {r!.verdict.includes("bunch")
              ? `The ${n} model was rejected: the day after a breach had a ${pct(m(r, "breach_rate_after_a_breach"), 0)} chance of another, against 5% expected. Its bad days came in bunches.`
              : r!.verdict.includes("avoid")
                ? `The ${n} model was rejected for the opposite reason: its breaches were spaced out more evenly than chance allows (${pct(m(r, "breach_rate_after_a_breach"), 0)} chance of one the day after another).`
                : `The ${n} model was rejected: ${r!.verdict.replace(/^Rejected:\s*/, "")}.`}
          </p>
        ))}
        {passed.map(([n, r]) => (
          <p key={n}>
            The {n} model passed both tests: about the right number of bad days ({pct(m(r, "breach_rate"))}), and no sign
            that one bad day made the next more likely ({pct(m(r, "breach_rate_after_a_breach"), 0)} the day after).
            {n === "EWMA" ? " It counts recent days more, so it raises its warning quickly once markets turn rough." : ""}
          </p>
        ))}
      </>
    ),
    quant: (
      <>
        <p>
          One-day 95% VaR of the equal-weight portfolio, forecast each day from the previous 500 returns with 10,000
          Monte Carlo draws: <em>historical</em> bootstraps the window; <em>normal</em> draws from N(μ̂, σ̂); <em>EWMA</em>{" "}
          draws from N(0, σ̂ₜ) with σ̂²ₜ = 0.94·σ̂²ₜ₋₁ + 0.06·r²ₜ₋₁ (RiskMetrics). The hit sequence is Iₜ = 1{"{"}rₜ &lt; −VaRₜ{"}"}.
        </p>
        <p>
          <strong>Kupiec POF:</strong> likelihood ratio of the hit rate x/n against p = 0.05, χ²(1). It tests the count
          only. <strong>Christoffersen independence:</strong> fits a two-state Markov chain to Iₜ and tests π₀₁ = π₁₁,
          χ²(1). It rejects in either direction, so it catches both clustering and breaches that avoid each other.
        </p>
        <Table
          head={["Model", "Hit rate", "Kupiec p", "Christoffersen p", "P(hit | hit)", "Extra loss on a hit"]}
          rows={models
            .filter(([, r]) => r)
            .map(([n, r]) => [
              n,
              pct(m(r, "breach_rate"), 2),
              fixed(m(r, "kupiec_p"), 3),
              fixed(m(r, "christoffersen_p"), 3),
              pct(m(r, "breach_rate_after_a_breach"), 1),
              pct(m(r, "average_excess_loss_on_breach"), 2),
            ])}
        />
        {failed.some(([, r]) => r!.verdict.includes("bunch")) && (
          <p>
            Reading: a model with the right unconditional rate can still fail independence when volatility clusters. A
            fixed 500-day window adapts slowly, so after a shock its forecast stays too small for several days running.
          </p>
        )}
        <p>Each test is run at 5% on three models, with no adjustment for multiple testing.</p>
      </>
    ),
  };
}

function pairsTrading(rows: Result[]): Both {
  const coint = find(rows, "cointegration");
  const dist = find(rows, "distance");
  const periods = m(coint, "net_sharpe_by_period") as Record<string, number> | undefined;
  return {
    plain: (
      <>
        <p>
          Some stocks move together, like two companies in the same industry. When they drift apart, you buy the cheaper
          one and sell the pricier one, betting the gap closes. Every six months we used the year before to choose 20
          pairs, then traded them.
        </p>
        <p>
          Before costs, the cointegration method made {pct(m(coint, "gross_annual_return"))} a year on average. Trading fees and
          the fee to borrow shares took {pct(m(coint, "cost_drag_annual"))}, leaving {pct(averageNet(coint))}. To pass it
          needed a score of 3; it got {fixed(m(coint, "choice_t"))}.
        </p>
        <p>
          A bet like this is meant to be safe from market swings, yet at its worst it was down{" "}
          {pct(s(coint)?.max_drawdown)}.
          {pass(coint) || pass(dist) ? "" : " So, on this data, there was no reliable edge."}
        </p>
      </>
    ),
    quant: (
      <>
        <p>
          Formation 252 days, trading 126, rolled every 126 days. Universe: point-in-time top 1,000 by SEC public float;
          pairs restricted to the same two-digit SIC code (Do & Faff, 2010).
        </p>
        <p>
          <strong>Distance</strong> (Gatev, Goetzmann & Rouwenhorst, 2006): the 20 pairs with the smallest sum of squared
          differences of normalised total-return indices; open when the gap exceeds 2 formation σ, close at the cross.{" "}
          <strong>Cointegration</strong> (Engle & Granger, 1987): log Pᴬ = α + β·log Pᴮ + ε, with an ADF test on ε at 5%,
          keeping the 20 lowest p-values; trade z = (ε − μ̂)/σ̂ with formation moments, open at |z| &gt; 2, close at z = 0,
          and hedge by β.
        </p>
        <p>
          Orders fill a day after the signal. Returns are on committed capital (÷ 20 pairs), net of 10 bp per trade and
          50 bp a year to borrow the short leg. Inference uses a Newey-West t on mean daily excess return over the choice
          years; the last two calendar years are held out and must be positive.
        </p>
        <Table
          head={["Method", "Sharpe ± SE", "Gross avg / yr", "Costs / yr", "Net avg / yr", "Net compound / yr", "Max drawdown", "t (choice)", "t (hold-out)", "Trades"]}
          rows={[
            ["Cointegration", coint],
            ["Distance", dist],
          ]
            .filter(([, r]) => r)
            .map(([n, r]) => {
              const x = r as Result;
              return [
                n as string,
                `${fixed(s(x)?.sharpe)} ± ${fixed(s(x)?.sharpe_se)}`,
                pct(m(x, "gross_annual_return")),
                pct(m(x, "cost_drag_annual")),
                pct(averageNet(x)),
                pct(s(x)?.annual_return),
                pct(s(x)?.max_drawdown),
                fixed(m(x, "choice_t")),
                fixed(m(x, "holdout_t")),
                String(m(x, "trades") ?? "—"),
              ];
            })}
        />
        {periods && (
          <p>
            Net Sharpe by period:{" "}
            {Object.entries(periods)
              .map(([k, v]) => `${k} ${fixed(v)}`)
              .join(" · ")}
            . A strong recent stretch doesn't count unless the full test passes. Picking the period after seeing the
            results is data snooping.
          </p>
        )}
        <p>
          Known biases: today's stock list (survivorship), and daily rebalanced legs rather than the paper's
          buy-and-hold legs.
        </p>
      </>
    ),
  };
}

function volTargeting(rows: Result[]): Both {
  const vm = find(rows, "variance-managed (Moreira-Muir)");
  const vt = find(rows, "volatility target");
  return {
    plain: (
      <>
        <p>
          When markets get stormy, this strategy holds less. When they're calm, it holds more, up to twice its money
          with borrowing. The idea, from a 2017 paper, is that stormy spells don't pay enough extra to be worth their risk.
        </p>
        <p>
          Return for each unit of risk: {fixed(s(vm)?.sharpe)} managed vs {fixed(b(vm)?.sharpe)} just holding. Worst
          fall: {pct(s(vm)?.max_drawdown)} vs {pct(b(vm)?.max_drawdown)}.{" "}
          {pass(vm) || pass(vt)
            ? "It also passed the test for extra return."
            : `To show real extra return it needed a score of 3; it got ${fixed(m(vm, "choice_t"))}. So it softened the crashes without adding return.`}
        </p>
      </>
    ),
    quant: (
      <>
        <p>
          Managed excess return fᵗᵐ = wₜ·fₜ. Variance-managed: wₜ = c / σ̂²ₜ₋₁. Volatility target: wₜ = σ* / σ̂ₜ₋₁. σ̂ is
          the realised volatility of the previous 21 daily excess returns (annualised), set at each month's first close
          and capped at 2×. c and σ* come from an expanding average of past risk, so nothing uses future data. Excess
          returns are over the Fed funds rate (lagged a day), and costs apply to every change in w.
        </p>
        <p>
          Test (Moreira & Muir, 2017): regress fᵗᵐ = α + β·f + ε, Newey-West t on α. A higher Sharpe alone isn't the
          test; α is.
        </p>
        <Table
          head={["Variant", "Sharpe ± SE", "Max drawdown", "α t (choice)", "t (hold-out)", "Avg exposure", "Max exposure"]}
          rows={[
            ["Variance-managed", vm],
            ["Volatility target", vt],
          ]
            .filter(([, r]) => r)
            .map(([n, r]) => {
              const x = r as Result;
              return [
                n as string,
                `${fixed(s(x)?.sharpe)} ± ${fixed(s(x)?.sharpe_se)}`,
                pct(s(x)?.max_drawdown),
                fixed(m(x, "choice_t")),
                fixed(m(x, "holdout_t")),
                `${fixed(m(x, "average_exposure"))}×`,
                `${fixed(m(x, "max_exposure"))}×`,
              ];
            })
            .concat(vm ? [["Unmanaged", `${fixed(b(vm)?.sharpe)} ± ${fixed(b(vm)?.sharpe_se)}`, pct(b(vm)?.max_drawdown), "—", "—", "1.00×", "1.00×"]] : [])}
        />
        <p>
          {lower(b(vm)?.max_drawdown, s(vm)?.max_drawdown)
            ? "Reading: the smaller drawdown is close to mechanical. Volatility persists, so exposure is already low when a sell-off deepens. "
            : "Reading: "}
          α needs more than lower risk: average returns must not rise in step with variance. Later work (DeMiguel et al.,
          2024) re-examines when this holds.
        </p>
      </>
    ),
  };
}

function trend(rows: Result[]): Both {
  const r = rows[0];
  return {
    plain: (
      <>
        <p>
          A simple rule: own a stock while its average price over the last 50 days is above its average over 200 days,
          which means it's trending up. Otherwise keep that money in cash.
        </p>
        <p>
          It earned {lower(s(r)?.sharpe, b(r)?.sharpe) ? "less" : "more"} for each unit of risk than holding everything (
          {fixed(s(r)?.sharpe)} vs {fixed(b(r)?.sharpe)}), and its worst fall was {pct(s(r)?.max_drawdown)} against{" "}
          {pct(b(r)?.max_drawdown)}.
          {lower(b(r)?.max_drawdown, s(r)?.max_drawdown) && lower(s(r)?.sharpe, b(r)?.sharpe)
            ? " Sitting in cash softened the crashes, but it also missed the rebounds."
            : ""}
        </p>
      </>
    ),
    quant: (
      <>
        <p>
          wᵢ,ₜ = 1{"{"}MA50ᵢ,ₜ &gt; MA200ᵢ,ₜ{"}"} / Nₜ over the point-in-time universe; the rest is cash earning nothing, which slightly flatters the baseline.
          Weights set at close t earn day t+1. Costs are 10 bp per unit of turnover, plus a 50 bp a year borrow fee on any short (none here). The baseline is equal weight in all
          Nₜ stocks.
        </p>
        <p>
          Test: Newey-West t on the mean daily return difference against the baseline over the choice years (t ≥ 3
          needed), then the sign over the two hold-out years.
        </p>
        {r && (
          <Table
            head={["", "Annual return", "Volatility", "Sharpe ± SE", "Max drawdown"]}
            rows={[
              ["Crossover", s(r)],
              ["Hold all", b(r)],
            ].map(([n, x]) => {
              const y = x as Summary | undefined;
              return [n as string, pct(y?.annual_return), pct(y?.annual_volatility), `${fixed(y?.sharpe)} ± ${fixed(y?.sharpe_se)}`, pct(y?.max_drawdown)];
            })}
          />
        )}
        <p>
          t (choice) = {fixed(m(r, "choice_t"))}, t (hold-out) = {fixed(m(r, "holdout_t"))}. The 50/200 values are the
          textbook ones and were never tuned, so there is no search to correct for.
        </p>
      </>
    ),
  };
}

function panic(rows: Result[]): Both {
  const r = rows[0];
  const choice = m(r, "choice") as Record<string, number> | undefined;
  const hold = m(r, "holdout") as Record<string, number> | undefined;
  const worst = m(r, "share_of_worst_5pct_months_after_shift");
  const share = m(r, "share_of_days_with_shift");
  const barelyBetter = num(worst) && num(share) && worst < 2 * share;
  return {
    plain: (
      <>
        <p>
          In a panic, everything falls together. So we measure how much stocks are moving as one, and raise a warning
          when that jumps. The question: after a warning, does the market do worse over the next month?
        </p>
        <p>
          Warnings were on for {pct(share, 0)} of days, and {pct(worst, 0)} of the worst months came with one.
          {barelyBetter ? " Because warnings were so common, that is not much better than chance." : ""}{" "}
          {pass(r)
            ? "The test found the market did worse after warnings."
            : `To pass it needed a score of 3; it got ${fixed(choice?.t)}. It spots a crash while it's happening, but it doesn't warn of the next one.`}
        </p>
      </>
    ),
    quant: (
      <>
        <p>
          Daily, on the trailing 63 days of returns for stocks with a full window: the correlation matrix's
          eigen-decomposition, and the absorption ratio AR = Σ top ⌊N/5⌋ eigenvalues / Σ all (Kritzman, Li, Page &
          Rigobon). A shift is the 15-day mean of AR at least one standard deviation above its 252-day mean.
        </p>
        <p>
          Test: regress the equal-weight market's next 21-day return on a shift dummy. Windows overlap, so the t uses
          Newey-West with 21 lags. A useful detector needs t ≤ −3 on the choice years and a lower mean on the hold-out.
        </p>
        <Table
          head={["Sample", "Days", "Days with a shift", "Return gap after a shift", "t"]}
          rows={[
            ["Choice years", choice],
            ["Hold-out", hold],
          ]
            .filter(([, x]) => x)
            .map(([n, x]) => {
              const y = x as Record<string, number>;
              return [n as string, String(y.days ?? "—"), String(y.shift_days ?? "—"), pct(y.gap_after_shift, 2), fixed(y.t)];
            })}
        />
        <p>
          {pass(r) ? "Reading: here a shift did lead lower returns. " : "Reading: on this data a shift does not lead the next month's return, so AR is at best a gauge of fragility as it happens. "}
          One fifth of eigenvectors and the one-standard-deviation trigger are fixed choices, not
          tuned.
        </p>
      </>
    ),
  };
}

export function explain(key: string, rows: Result[]): Both | null {
  if (key === "value_at_risk") return valueAtRisk(rows);
  if (key === "pairs_trading") return pairsTrading(rows);
  if (key === "vol_targeting") return volTargeting(rows);
  if (key === "ma_crossover") return trend(rows);
  if (key === "panic_detector") return panic(rows);
  return null;
}
