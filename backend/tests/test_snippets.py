"""The dashboard's code panels must match the code that actually ran."""

import json

from stockintel import snippets


def test_dashboard_code_panels_match_the_real_functions():
    shown = json.loads(snippets.OUT.read_text())
    assert shown == snippets.build(), "Run: python -m stockintel.snippets"
