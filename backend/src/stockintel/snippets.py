"""Copy the core function of each study into the dashboard, exactly as written.

The dashboard shows real code, not a rewrite. A test fails if frontend/src/snippets.json no
longer matches these functions. Run after changing a study:
python -m stockintel.snippets
"""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "frontend" / "src" / "snippets.json"
QUANT = Path(__file__).resolve().parent / "quant"

# Study -> (file, functions to show), in the order they appear.
CHOSEN = {
    "ma_crossover": ("studies.py", ["ma_crossover"]),
    "vol_targeting": ("vol.py", ["conditional_held", "ewma_held"]),
    "pairs_trading": ("pairs.py", ["coint_pairs", "positions"]),
    "value_at_risk": ("var.py", ["garch_volatility", "forecasts"]),
    "panic_detector": ("panic.py", ["readings"]),
    "market_century": ("studies.py", ["trend_on", "trend_returns"]),
    "momentum": ("studies.py", ["momentum"]),
    "low_volatility": ("studies.py", ["low_volatility"]),
    "factor_momentum": ("studies.py", ["factor_momentum"]),
    "mean_reversion": ("studies.py", ["mean_reversion"]),
    "breakout": ("studies.py", ["_channel", "breakout"]),
}


def extract(path: Path, names: list[str]) -> str:
    source = path.read_text()
    lines = source.splitlines()
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            found[node.name] = "\n".join(lines[node.lineno - 1 : node.end_lineno])
    missing = [n for n in names if n not in found]
    if missing:
        raise KeyError(f"{path.name}: {missing} not found")
    return "\n\n\n".join(found[n] for n in names)


def build() -> dict[str, dict[str, str]]:
    return {
        study: {
            "file": f"backend/src/stockintel/quant/{file}",
            "code": extract(QUANT / file, names),
        }
        for study, (file, names) in CHOSEN.items()
    }


def main() -> None:
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
