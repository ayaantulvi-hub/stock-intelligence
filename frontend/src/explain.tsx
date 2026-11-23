import type { ReactNode } from "react";
import { PASSING, type Result, type Summary } from "./api";
import { fixed, NOT_VERIFIED, num, pct } from "./format";
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
const anyPassOf = (list: [string, Result][]) => list.some(([, r]) => pass(r));

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
    ["Filtered historical", find(rows, "filtered historical")],
    ["GJR-GARCH-t", find(rows, "gjr-garch t")],
  ] as const;
  const why: Record<string, string> = {
    EWMA: " It counts recent days more, so it raises its warning quickly once markets turn rough.",
    "Filtered historical":
      " It replays real past days, resized to today's level of calm or storm, so it keeps the real shape of bad days without assuming a bell curve.",
    "GJR-GARCH-t":
      " Its risk estimate jumps more after falls than after rises, and it allows for rare, extreme days.",
  };
  const failed = models.filter(([, r]) => r && !pass(r));
  const passed = models.filter(([, r]) => r && pass(r));
  const days = m(models.find(([, r]) => r)?.[1], "days");
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
          danger is highest. The first three models are the classics. The last two are newer versions built to react to
          changing risk and to allow for extreme days.
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
            {why[n] ?? ""}
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
          <strong>Filtered historical</strong> (after Hull & White, 1998): bootstrap the standardised returns zₛ = rₛ / σ̂ₛ
          from the window, then rescale by today's σ̂ₜ, with σ̂ the same EWMA. <strong>GJR-GARCH-t</strong> (Glosten,
          Jagannathan & Runkle, 1993): σ²ₜ = ω + (α + γ·1{"{"}εₜ₋₁ &lt; 0{"}"})·ε²ₜ₋₁ + β·σ²ₜ₋₁ with standardised Student-t shocks,
          fitted by maximum likelihood on the 500 days before each refit (every 21 days) and run forward on real returns in
          between. Both have no settings chosen from results: 0.94, 500 and 21 were fixed in advance.
        </p>
        <p>
          <strong>Kupiec POF:</strong> likelihood ratio of the hit rate x/n against p = 0.05, χ²(1). It tests the count
          only. <strong>Christoffersen independence:</strong> fits a two-state Markov chain to Iₜ and tests π₀₁ = π₁₁,
          χ²(1). It rejects in either direction, so it catches both clustering and breaches that avoid each other. <strong>Joint
          (conditional coverage):</strong> both at once, χ²(2). It is reported for reference; the verdict uses the two separate
          tests, as set before the results were seen.
        </p>
        <Table
          head={["Model", "Hit rate", "Kupiec p", "Christoffersen p", "Joint p", "P(hit | hit)", "Extra loss on a hit"]}
          rows={models
            .filter(([, r]) => r)
            .map(([n, r]) => [
              n,
              pct(m(r, "breach_rate"), 2),
              fixed(m(r, "kupiec_p"), 3),
              fixed(m(r, "christoffersen_p"), 3),
              num(m(r, "conditional_coverage_p")) ? fixed(m(r, "conditional_coverage_p"), 3) : "Not run yet",
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
        {num(m(find(rows, "gjr-garch t"), "fit_failures")) && (m(find(rows, "gjr-garch t"), "fit_failures") as number) > 0 && (
          <p>
            GARCH fits that failed to converge: {String(m(find(rows, "gjr-garch t"), "fit_failures"))}. Each kept the last good
            parameters.
          </p>
        )}
        <p>Each test is run at 5% on {models.filter(([, r]) => r).length} models, with no adjustment for multiple testing.</p>
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
  const versions = [
    ["Variance-managed", find(rows, "variance-managed (Moreira-Muir)")],
    ["Volatility target", find(rows, "volatility target")],
    ["Conditional", find(rows, "conditional (Bongaerts et al.)")],
    ["Daily EWMA", find(rows, "daily EWMA (Harvey et al.)")],
  ].filter(([, r]) => r) as [string, Result][];
  const smaller = versions.filter(([, r]) => lower(b(r)?.max_drawdown, s(r)?.max_drawdown)).map(([n]) => n);
  const best = [...versions].sort(([, x], [, y]) => ((m(y, "choice_t") as number) ?? -Infinity) - ((m(x, "choice_t") as number) ?? -Infinity))[0];
  return {
    plain: (
      <>
        <p>
          When markets get stormy, these strategies hold less. When they're calm, they hold more, up to twice the money
          with borrowing. The idea is that stormy spells don't pay enough extra to be worth their risk.
        </p>
        <p>We test four ways of doing it:</p>
        <ul className="plain-list">
          <li><strong>Variance-managed</strong> and <strong>volatility target:</strong> resize once a month, based on how jumpy last month was.</li>
          <li><strong>Conditional:</strong> leave things alone in ordinary months, and act only when last month was unusually calm or unusually wild.</li>
          <li><strong>Daily EWMA:</strong> resize every day, giving the most recent days the most weight, so it reacts within days rather than weeks.</li>
        </ul>
        <p>
          Each is compared with just holding the market over the same years.{" "}
          {smaller.length
            ? `${smaller.join(", ")} cut the worst fall.`
            : "None of them cut the worst fall."}{" "}
          {anyPassOf(versions)
            ? "At least one also passed the test for real extra return."
            : `None passed the test for real extra return: that needs a score of 3, and the best, ${best?.[0] ?? NOT_VERIFIED}, got ${fixed(m(best?.[1], "choice_t"))}.`}
        </p>
      </>
    ),
    quant: (
      <>
        <p>
          Managed excess return fᵗᵐ = wₜ·fₜ, capped at 2×, with costs on every change in w and excess returns over the Fed
          funds rate (lagged a day). <strong>Variance-managed</strong> (Moreira & Muir, 2017): wₜ = c / σ̂²ₘ₋₁.{" "}
          <strong>Volatility target:</strong> wₜ = σ* / σ̂ₘ₋₁. Both use the previous month's 21 daily returns, set at the
          month's first close; c and σ* are expanding averages of past risk.
        </p>
        <p>
          <strong>Conditional</strong> (Bongaerts, Kang & van Dijk, 2020): σ̂ₘ₋₁ from last month without its final day; scale
          to σ* / σ̂ₘ₋₁ only if σ̂ₘ₋₁ is in the top or bottom fifth of all earlier monthly readings, else w = 1. σ* is the
          volatility of all earlier daily returns. The paper wants 10 years of history; with 16 years of data we use 5,
          fixed in advance. <strong>Daily EWMA</strong> (Harvey et al., 2018): σ̂ₜ from zero-mean squared returns with a
          20-day half-life, rebalanced daily. The paper scales on the full sample; here the target is the average of past
          σ̂ only, which is the real-time standard Cederburg et al. (2020) argue for.
        </p>
        <p>
          Test (Moreira & Muir): regress fᵗᵐ = α + β·f + ε, Newey-West t on α. A higher Sharpe alone isn't the test; α is.
        </p>
        <Table
          head={["Version", "From", "Sharpe ± SE", "Holding, same years", "Max drawdown", "Holding, same years", "α t (choice)", "t (hold-out)", "Avg / max exposure"]}
          rows={versions.map(([n, x]) => [
            n,
            x.period.slice(0, 4),
            `${fixed(s(x)?.sharpe)} ± ${fixed(s(x)?.sharpe_se)}`,
            fixed(b(x)?.sharpe),
            pct(s(x)?.max_drawdown),
            pct(b(x)?.max_drawdown),
            fixed(m(x, "choice_t")),
            fixed(m(x, "holdout_t")),
            `${fixed(m(x, "average_exposure"))}× / ${fixed(m(x, "max_exposure"))}×`,
          ])}
        />
        <p>
          {smaller.length
            ? "Reading: drawdown cuts are close to mechanical, because volatility persists and exposure is already low when a sell-off deepens. "
            : "Reading: "}
          α needs more: average returns must not rise in step with variance. Each version is compared with holding over its
          own years, because each needs a different warm-up.
        </p>
      </>
    ),
  };
}

/** Years of data a t-score would need to reach 3 at the same strength: t grows with the
 * square root of the sample, so years × (3 / t)². Arithmetic on stored figures only. */
function yearsToThree(r?: Result): number | null {
  const t = m(r, "choice_t");
  const start = r?.period.slice(0, 4);
  if (!num(t) || t <= 0 || !start) return null;
  const years = HOLDOUT_START - Number(start);
  return years * (3 / t) ** 2;
}
const HOLDOUT_START = 2025; // The last two calendar years are held back.

function century(rows: Result[]): Both {
  const versions = [
    ["Variance-managed", find(rows, "variance-managed (Moreira-Muir)")],
    ["Volatility target", find(rows, "volatility target")],
    ["Conditional", find(rows, "conditional (Bongaerts et al.)")],
    ["Daily EWMA", find(rows, "daily EWMA (Harvey et al.)")],
    ["Trend 50/200", find(rows, "trend 50/200")],
  ].filter(([, r]) => r) as [string, Result][];
  const targeting = versions.filter(([n]) => n !== "Trend 50/200");
  const best = [...targeting].sort(([, x], [, y]) => ((m(y, "choice_t") as number) ?? -Infinity) - ((m(x, "choice_t") as number) ?? -Infinity))[0];
  const need = yearsToThree(best?.[1]);
  const holdoutNegative = versions.filter(([, r]) => num(m(r, "holdout_gain_daily")) && (m(r, "holdout_gain_daily") as number) <= 0).map(([n]) => n);
  return {
    plain: (
      <>
        <p>
          On 16 years of data, a small edge can't prove itself: luck alone moves results that much. So we ran exactly the
          same rules, with the same costs and the same pass mark, on the whole US stock market every day since 1926.
          Nothing was changed except the amount of history.
        </p>
        <p>
          The best volatility version, {best?.[0] ?? NOT_VERIFIED}, scored{" "}
          {fixed(m(best?.[1], "choice_t"))} against a pass mark of 3.
          {need ? ` At that strength it would need roughly ${Math.round(need / 10) * 10} years of data to reach 3.` : ""}
          {holdoutNegative.length ? ` It also has to do well on the two held-back years, and ${holdoutNegative.join(", ")} didn't.` : ""}
        </p>
        <p>
          {anyPassOf(versions)
            ? "At least one version passed both checks."
            : num(m(best?.[1], "choice_t")) && (m(best?.[1], "choice_t") as number) >= 2
              ? "So the honest reading is: probably a small real effect, but not proven by this test."
              : "So even a century of data shows no sign of a reliable edge."}
        </p>
      </>
    ),
    quant: (
      <>
        <p>
          Data: daily Mkt-RF and RF from the Kenneth R. French Data Library (value-weighted CRSP NYSE, AMEX and NASDAQ firms
          minus the one-month T-bill). The four targeting rules are the same functions as the main study, with the same
          settings, 2× cap and 10 bp costs. Trend 50/200 holds the market while its 50-day average of total-return level is
          above the 200-day, else T-bills; it is judged by the mean daily gain over holding, like the stock-level trend
          study.
        </p>
        <p>
          Same verdict rule: Newey-West t ≥ 3 on the choice years and a positive result on the last two calendar years.
          Under Newey-West the t-score grows roughly with √T, so for a fixed effect size the years needed scale as
          T × (3 / t)².
        </p>
        <Table
          head={["Version", "From", "Sharpe ± SE", "Holding", "Max drawdown", "Holding", "t (choice)", "t (hold-out)"]}
          rows={versions.map(([n, x]) => [
            n,
            x.period.slice(0, 4),
            `${fixed(s(x)?.sharpe)} ± ${fixed(s(x)?.sharpe_se)}`,
            fixed(b(x)?.sharpe),
            pct(s(x)?.max_drawdown),
            pct(b(x)?.max_drawdown),
            fixed(m(x, "choice_t")),
            fixed(m(x, "holdout_t")),
          ])}
        />
        <p>
          Reading: Moreira and Muir report a positive market alpha on similar data, in-sample, with a scale set on the full
          sample. Here every scale and threshold uses only past data, which Cederburg et al. (2020) found weakens real-time
          results. The gap between those two is the price of doing it without hindsight.
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
  if (key === "market_century") return century(rows);
  if (key === "panic_detector") return panic(rows);
  return null;
}
