"""Plain-English strengths, weaknesses and cautions for each model type."""

TEAM = "Team of models"

PROFILES = {
    "Linear model": {
        "good": "Simple, stable and easy to explain.",
        "bad": "Misses factors that only matter together.",
        "caution": "Can be right on average and still miss turning points.",
    },
    "Random forest": {
        "good": "Averages many simple rules, so it resists noise.",
        "bad": "Slow, and weak at conditions it has not seen.",
        "caution": "Its answers bunch up, so don't read small gaps between stocks as real.",
    },
    "Gradient boosting": {
        "good": "Finds combinations of factors, and copes with missing data.",
        "bad": "Learns past noise easily if left unchecked.",
        "caution": "Strong past results can be overfitting, so trust the hold-out test.",
    },
    "Neural network": {
        "good": "Can learn complicated patterns.",
        "bad": "Needs a lot of data, changes with small changes, and is hard to explain.",
        "caution": "Market data is mostly noise, which suits it poorly.",
    },
    "Families, equal weight": {
        "good": "Averages a few clear ideas, so noise has little room. Often hard to beat.",
        "bad": "Every family counts the same, even if one matters more.",
        "caution": "Only as good as the factors that pass into each family.",
    },
    "Families, linear": {
        "good": "Learns how much each family matters, and stays simple to explain.",
        "bad": "Misses families that only matter together.",
        "caution": "Weights can shift from year to year with noisy data.",
    },
    "Families, boosted": {
        "good": "Can find families that matter only together, on few inputs.",
        "bad": "More room to learn past noise than a plain average.",
        "caution": "Trust it only if it beats the plain average on the hold-out years.",
    },
    TEAM: {
        "good": "Averaging different models cancels some of each one's mistakes.",
        "bad": "Harder to explain, and can't beat its members by much.",
        "caution": "If all the models share a blind spot, so does the team.",
    },
}
