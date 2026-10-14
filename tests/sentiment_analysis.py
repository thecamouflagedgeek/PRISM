"""Privacy-safe metadata audit; no sentiment model is trained or inferred.

The previous exploratory script leaked row-level loan descriptions and income
into stdout and called a mixed label heuristic a portfolio risk score. Dataset
provenance and sentiment-label semantics are not established, so this command
reports only aggregate schema checks and no model metrics.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from features.portfolio_sentiment import audit_sentiment_dataset


def main() -> None:
    dataset = Path(__file__).parent / "dataset" / "sentiment.csv"
    report = audit_sentiment_dataset(dataset)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
