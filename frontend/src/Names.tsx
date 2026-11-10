import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** Company names by ticker, from the stored SEC EDGAR list. Empty until loaded. */
const NamesContext = createContext<Record<string, string>>({});

export function NamesProvider({ children }: { children: ReactNode }) {
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    fetch("/api/names")
      .then((r) => (r.ok ? r.json() : {}))
      .then(setNames)
      .catch(() => setNames({}));
  }, []);
  return <NamesContext.Provider value={names}>{children}</NamesContext.Provider>;
}

const ENDINGS = /[,.]?\s+(inc|corp|corporation|co|company|ltd|limited|plc|holdings?|group|n\.?v|s\.?a|ag|se|lp|l\.?p|\/?de|\/?mn|\/?md|class [a-c])\.?$/i;

/** "NVIDIA CORP" becomes "Nvidia"; short and readable next to the ticker. */
export function shortName(name: string): string {
  let out = name.trim();
  for (let i = 0; i < 4; i++) out = out.replace(ENDINGS, "").trim();
  if (out === out.toUpperCase() && /[A-Z]{4,}/.test(out)) {
    out = out.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return out.length > 28 ? `${out.slice(0, 26)}…` : out;
}

export function useName(ticker: string): string | null {
  const names = useContext(NamesContext);
  const name = names[ticker];
  return name ? shortName(name) : null;
}

/** A ticker with its company name beside it, when the name is known. */
export function Tick({ t }: { t: string }) {
  const name = useName(t);
  return (
    <>
      {t}
      {name && <span className="company"> {name}</span>}
    </>
  );
}
