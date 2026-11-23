export const NOT_VERIFIED = "Not verified";

export function num(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function pct(value: unknown, digits = 1, signed = false): string {
  if (!num(value)) return NOT_VERIFIED;
  const text = `${(value * 100).toFixed(digits)}%`;
  return signed && value > 0 ? `+${text}` : text.replace("-", "−");
}

export function fixed(value: unknown, digits = 2): string {
  return num(value) ? value.toFixed(digits).replace("-", "−") : NOT_VERIFIED;
}

export function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return new Date(Number(year), Number(m) - 1).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}
