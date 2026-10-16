# tests the evaluation metrics on the admin page: the math is right on a tiny
# made-up example, and the api only shows it to logged in admins.

from findit.evaluation import evaluation, intent_metrics
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


def test_real_test_set_runs():
    report = evaluation()["intent"]
    assert report["total"] > 100
    assert report["accuracy"] > 80


def test_evaluation_needs_login(client):  # noqa: F811
    assert client.get("/api/admin/evaluation").status_code == 401
    login(client)
    data = client.get("/api/admin/evaluation").get_json()
    assert set(data) == {"intent"}
