"""Rules from the build brief that can be checked against the code itself."""

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = Path(__file__).resolve().parents[2]


def test_production_code_never_imports_tests():
    for path in SRC.rglob("*.py"):
        source = path.read_text()
        assert "from tests" not in source and "import tests" not in source, path


def test_env_file_is_ignored_by_git():
    assert ".env" in (ROOT / ".gitignore").read_text().splitlines()
