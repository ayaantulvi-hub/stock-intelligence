"""Company data checks. Every report here is a TEST FIXTURE."""

from datetime import date

from stockintel.audit import check

TODAY = date(2026, 11, 4)
RECENT = date(2026, 1, 25)


def metric(name, value, period=RECENT):
    return {"name": name, "value": value, "sources": [{"period_end": period}]}


def report(*items):
    return {"available": True, "metrics": list(items)}


def good():
    return report(
        metric("Revenue", 200.0),
        metric("Net income", 100.0),
        metric("Gross profit", 150.0),
        metric("Gross margin", 0.75),
    )


def test_sound_figures_pass():
    assert check(good(), TODAY) == []


def test_the_nvda_bug_would_be_caught():
    found = check(
        report(
            metric("Revenue", 26.9, date(2022, 1, 30)),
            metric("Net income", 120.0),
            metric("Gross profit", 153.0),
            metric("Gross margin", 5.7),
        ),
        TODAY,
    )
    assert "Revenue and net income come from different years." in found
    assert "Gross margin is outside what is possible." in found


def test_old_figures_are_flagged():
    found = check(
        report(
            metric("Revenue", 1.0, date(2023, 1, 1)), metric("Net income", 1.0, date(2023, 1, 1))
        ),
        TODAY,
    )
    assert "The latest yearly figures are over 500 days old." in found


def test_missing_figures_are_flagged():
    assert "Revenue could not be found." in check(report(metric("Net income", 1.0)), TODAY)
    assert check({"available": False}, TODAY) == ["No company figures are stored."]


def test_a_company_with_nothing_on_sale_is_not_flagged():
    assert check(report(metric("Revenue", 0.0), metric("Net income", -5.0)), TODAY) == []


def test_a_large_loss_is_not_flagged():
    assert check(report(metric("Revenue", 1.0), metric("Net income", -8.0)), TODAY) == []


def test_figures_from_different_years_are_not_compared_for_size():
    found = check(
        report(
            metric("Revenue", 10.0, date(2025, 1, 25)),
            metric("Net income", 40.0),
            metric("Gross profit", 30.0),
        ),
        TODAY,
    )
    assert found == ["Revenue and net income come from different years."]
