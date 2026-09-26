# checks our plain python classifier gives the same answers as scikit-learn,
# plus a few messages that must always be classified right.

import json
from pathlib import Path

import pytest

from findit.classifier import IntentClassifier

FIXTURE = Path(__file__).parent / "fixtures" / "parity.json"


@pytest.fixture(scope="module")
def clf():
    return IntentClassifier()


def test_matches_sklearn(clf):
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for row in rows:
        ours = clf.predict_proba(row["text"])
        for label, p in row["probs"].items():
            # json weights are rounded to 6 decimals so allow a tiny gap
            assert ours[label] == pytest.approx(p, abs=1e-3), row["text"]


@pytest.mark.parametrize("text,intent", [
    ("i lost my wallet in the library", "REPORT_LOST"),
    ("I found a telecommunication device inside the gym", "REPORT_FOUND"),
    ("did anyone turn in an umbrella?", "SEARCH_ITEM"),
    ("where is the lost and found office?", "GENERAL_INQUIRY"),
    ("nawala ko yung payong ko", "REPORT_LOST"),
    ("may nakita akong wallet sa cr", "REPORT_FOUND"),
])
def test_basic_intents(clf, text, intent):
    assert clf.predict(text)[0] == intent
