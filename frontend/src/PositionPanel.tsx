import { useEffect, useState, type FormEvent } from "react";

type Position = {
  shares: number;
  buy_price: number;
  target_price: number | null;
  stop_price: number | null;
  price: number | null;
  cost?: number;
  worth?: number;
  profit?: number;
  profit_percent?: number;
  break_even?: number;
  above_break_even?: boolean;
  plan?: string;
  call?: string;
  cases?: { name: string; value: number; from_cost: number }[];
};

const blank = { shares: "", buy_price: "", target_price: "", stop_price: "" };
const FIELDS: [keyof typeof blank, string][] = [
  ["shares", "Shares"],
  ["buy_price", "Price paid"],
  ["target_price", "Sell target (optional)"],
  ["stop_price", "Stop price (optional)"],
];

export default function PositionPanel({
  ticker,
  onChange,
}: {
  ticker: string;
  onChange?: () => void;
}) {
  const url = `/api/stocks/${encodeURIComponent(ticker)}/position`;
  const [position, setPosition] = useState<Position | null>(null);
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    setEditing(false);
    fetch(url)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setPosition)
      .catch(() => setFailed(true));
  }, [url]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const number = (value: string) => (value === "" ? null : Number(value));
    try {
      const response = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shares: number(form.shares),
          buy_price: number(form.buy_price),
          target_price: number(form.target_price),
          stop_price: number(form.stop_price),
        }),
      });
      if (response.status !== 200) throw new Error();
      setPosition(await response.json());
      setEditing(false);
      setFailed(false);
      onChange?.();
    } catch {
      setFailed(true);
    }
  };

  const remove = async () => {
    try {
      const response = await fetch(url, { method: "DELETE" });
      if (response.status !== 200) throw new Error();
      setPosition(null);
      setForm(blank);
      onChange?.();
    } catch {
      setFailed(true);
    }
  };

  const edit = () => {
    if (position) {
      setForm({
        shares: String(position.shares),
        buy_price: String(position.buy_price),
        target_price: position.target_price === null ? "" : String(position.target_price),
        stop_price: position.stop_price === null ? "" : String(position.stop_price),
      });
    }
    setEditing(true);
  };

  return (
    <div className="position">
      {failed && <p className="bad">Could not load or save this. Not verified.</p>}
      {editing ? (
        <form onSubmit={save} className="inputs">
          {FIELDS.map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                step="any"
                min="0"
                required={key === "shares" || key === "buy_price"}
                value={form[key]}
                onChange={(event) => setForm({ ...form, [key]: event.target.value })}
              />
            </label>
          ))}
          <button type="submit">Save</button>
        </form>
      ) : !position ? (
        <button onClick={edit}>I own this</button>
      ) : position.price === null || position.profit === undefined ? (
        <p>Not verified: no price stored for this stock yet.</p>
      ) : (
        <>
          <div className="glance">
            <div>
              <small>Paid</small>
              <strong>{position.buy_price.toFixed(2)}</strong>
            </div>
            <div>
              <small>Latest close</small>
              <strong>{position.price.toFixed(2)}</strong>
            </div>
            <div>
              <small>Profit or loss</small>
              <strong className={position.profit >= 0 ? "ok" : "bad"}>
                {position.profit >= 0 ? "+" : "-"}${Math.abs(position.profit).toFixed(2)} (
                {position.profit_percent?.toFixed(1)}%)
              </strong>
            </div>
            <div>
              <small>Break-even after costs</small>
              <strong>{position.break_even?.toFixed(2)}</strong>
            </div>
            {position.cases?.map((item) => (
              <div key={item.name}>
                <small>{item.name} value against what you paid</small>
                <strong>
                  ${item.value.toFixed(2)} ({(item.from_cost * 100).toFixed(0)}%)
                </strong>
              </div>
            ))}
          </div>
          <p>
            <strong>Your plan:</strong> {position.plan}
          </p>
          <p>
            <strong>The model:</strong> {position.call}
          </p>
          <small>
            What you paid changes your profit, not where the stock goes next. So it never changes
            the model's call. Set your target and stop before emotions get involved.
          </small>
          <div className="tabs">
            <button onClick={edit}>Edit</button>
            <button onClick={remove}>I no longer own this</button>
          </div>
        </>
      )}
    </div>
  );
}
