# evaluation metrics for the admin page. runs the intent classifier on handwritten
# messages it never trained on and scores it: accuracy, precision, recall, f1 and a
# confusion matrix. this is how we show how good the nlp actually is.

import csv
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def read_csv(name):
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct(n, total):
    return round(100 * n / total, 1) if total else 0.0


def intent_metrics(clf, rows, threshold):
    truth = [r["intent"] for r in rows]
    preds = [clf.predict(r["text"]) for r in rows]
    guess = [p[0] for p in preds]
    labels = sorted(set(truth) | set(guess))

    # confusion matrix: rows = real intent, columns = what the model said
    matrix = [[sum(1 for t, g in zip(truth, guess) if t == a and g == b) for b in labels] for a in labels]

    per_class = []
    for i, label in enumerate(labels):
        tp = matrix[i][i]
        predicted = sum(matrix[r][i] for r in range(len(labels)))  # tp + fp
        actual = sum(matrix[i])  # tp + fn
        p = tp / predicted if predicted else 0
        r = tp / actual if actual else 0
        f1 = 2 * p * r / (p + r) if p + r else 0
        per_class.append({"intent": label, "precision": round(100 * p, 1), "recall": round(100 * r, 1),
                          "f1": round(100 * f1, 1), "support": actual})

    correct = sum(t == g for t, g in zip(truth, guess))
    # the bot only acts on its guess when it's confident enough, otherwise it asks the user
    sure = [(t, g) for t, (g, c) in zip(truth, preds) if c >= threshold]
    macro = lambda key: round(sum(c[key] for c in per_class) / len(per_class), 1) if per_class else 0  # noqa: E731

    return {
        "total": len(rows),
        "accuracy": pct(correct, len(rows)),
        "precision": macro("precision"),
        "recall": macro("recall"),
        "f1": macro("f1"),
        "avg_confidence": pct(sum(c for _, c in preds), len(rows)),
        "threshold": round(100 * threshold),
        "coverage": pct(len(sure), len(rows)),
        "confident_accuracy": pct(sum(t == g for t, g in sure), len(sure)),
        "labels": labels,
        "matrix": matrix,
        "per_class": per_class,
    }


@lru_cache(maxsize=1)
def evaluation():
    # the test set doesn't change while the site is running, so only score it once
    from .dialogue import MIN_CONFIDENCE, clf
    return {"intent": intent_metrics(clf, read_csv("test_intents.csv"), MIN_CONFIDENCE)}
