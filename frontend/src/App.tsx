import { useEffect, useState } from "react";

type Status = {
  healthy: boolean;
  checked_at: string;
  database: { state: string; detail: string | null };
  migrations: { state: string; current: string | null; expected: string | null };
  worker: { state: string; last_heartbeat: string | null; age_seconds: number | null };
};

const LABELS: Record<string, string> = {
  ok: "OK",
  error: "Error",
  stale: "Stale",
  never_run: "Never run",
  not_verified: "Not verified",
};

function Row({ name, state }: { name: string; state: string }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd className={state === "ok" ? "ok" : "bad"}>{LABELS[state] ?? "Not verified"}</dd>
    </div>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        // A 503 still carries a valid status body, which is shown as it is.
        const response = await fetch("/api/status");
        if (response.status !== 200 && response.status !== 503) throw new Error();
        setStatus(await response.json());
        setFailed(false);
      } catch {
        setStatus(null);
        setFailed(true);
      }
    };
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  return (
    <main>
      <h1>Stock Intelligence</h1>
      <p>System status. No market data is connected yet.</p>
      {failed && <p className="bad">Cannot reach the API. Status is not verified.</p>}
      {!failed && !status && <p>Checking…</p>}
      {status && (
        <dl>
          <Row name="Database" state={status.database.state} />
          <Row name="Database schema" state={status.migrations.state} />
          <Row name="Worker" state={status.worker.state} />
        </dl>
      )}
    </main>
  );
}
