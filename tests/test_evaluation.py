# tests the evaluation metrics on the admin page: the math is right on a tiny
# made-up example, and the api only shows it to logged in admins.

from findit.evaluation import intent_metrics, live_metrics, offline_report
from tests.test_admin import client, login  # noqa: F401


class FakeClassifier:
    def __init__(self, answers):
        self.answers = answers

    def predict(self, text):
        return self.answers[text]


def test_intent_math():
    rows = [{"text": "a", "intent": "LOST"}, {"text": "b", "intent": "LOST"},
            {"text": "c", "intent": "FOUND"}, {"text": "d", "intent": "FOUND"}]
    clf = FakeClassifier({"a": ("LOST", 0.9), "b": ("FOUND", 0.4), "c": ("FOUND", 0.8), "d": ("FOUND", 0.7)})
    m = intent_metrics(clf, rows, threshold=0.5)
    assert m["accuracy"] == 75.0
    assert m["labels"] == ["FOUND", "LOST"]
    assert m["matrix"] == [[2, 0], [1, 1]]
    found, lost = m["per_class"]
    assert (found["precision"], found["recall"]) == (66.7, 100.0)
    assert (lost["precision"], lost["recall"]) == (100.0, 50.0)
    assert m["coverage"] == 75.0 and m["confident_accuracy"] == 100.0
    assert len(m["mistakes"]) == 1


def test_live_numbers_skip_rule_messages():
    logs = [{"intent": "REPORT_LOST", "confidence": 0.9}, {"intent": "REPORT_LOST", "confidence": 0.3},
            {"intent": "GREETING", "confidence": None}]
    m = live_metrics(logs, 0.5)
    assert m["messages"] == 2 and m["low_confidence"] == 50.0


def test_real_test_sets_run():
    report = offline_report()
    assert report["intent"]["total"] > 100
    assert report["intent"]["accuracy"] > 80
    assert report["entities"]["total"] > 0 and report["faq"]["total"] > 0


def test_evaluation_needs_login(client):  # noqa: F811
    assert client.get("/api/admin/evaluation").status_code == 401
    login(client)
    data = client.get("/api/admin/evaluation").get_json()
    assert set(data) == {"intent", "entities", "faq", "live"}
