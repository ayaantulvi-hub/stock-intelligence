import { useMemo, useState } from "react";

/** A read-only code panel with simple Python highlighting. The code is the real function from
 * the repository (see backend/src/stockintel/snippets.py), never a rewrite. */

const KEYWORDS = new Set([
  "def", "return", "if", "elif", "else", "for", "in", "and", "or", "not", "is", "None", "True", "False",
  "import", "from", "as", "while", "continue", "break", "with", "lambda", "raise", "try", "except", "class",
]);

type Token = { text: string; kind: string };

function tokenize(line: string): Token[] {
  const out: Token[] = [];
  const pattern = /("""[\s\S]*?"""|"[^"]*"|'[^']*'|#.*$|\b\d+(?:\.\d+)?(?:e-?\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b|\s+|.)/g;
  let match: RegExpExecArray | null;
  let previous = "";
  while ((match = pattern.exec(line))) {
    const text = match[0];
    let kind = "plain";
    if (text.startsWith("#")) kind = "comment";
    else if (text.startsWith('"') || text.startsWith("'")) kind = "string";
    else if (/^\d/.test(text)) kind = "number";
    else if (KEYWORDS.has(text)) kind = "keyword";
    else if (previous === "def") kind = "function";
    if (text.trim()) previous = text;
    out.push({ text, kind });
  }
  return out;
}

export default function Code({ file, code }: { file: string; code: string }) {
  const [open, setOpen] = useState(false);
  const lines = useMemo(() => code.split("\n"), [code]);
  const shown = open ? lines : lines.slice(0, 18);
  return (
    <figure className="code">
      <figcaption>
        <a href={`https://github.com/ayaantulvi-hub/stock-intelligence/blob/main/${file}`} target="_blank" rel="noreferrer">
          {file}
        </a>
      </figcaption>
      <pre>
        <code>
          {shown.map((line, i) => (
            <span key={i} className="code-line">
              {tokenize(line).map((t, k) => (
                <span key={k} className={`tk-${t.kind}`}>
                  {t.text}
                </span>
              ))}
              {"\n"}
            </span>
          ))}
        </code>
      </pre>
      {lines.length > 18 && (
        <button className="more" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Show less" : `Show all ${lines.length} lines`}
        </button>
      )}
    </figure>
  );
}
