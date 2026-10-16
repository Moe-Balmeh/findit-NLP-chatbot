# evaluation metrics for the admin page. runs our nlp on test sets it never trained on
# and scores it: accuracy, precision, recall, f1 and a confusion matrix for the intent
# classifier, accuracy for entity extraction and the faq search, plus confidence
# numbers from real chats. this is how we show how good the nlp actually is.

import csv
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .labels import item_name, location_name

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
        "mistakes": [{"text": r["text"], "expected": t, "predicted": g, "confidence": round(100 * c)}
                     for r, t, (g, c) in zip(rows, truth, preds) if t != g],
    }


def entity_metrics(extract, rows):
    # empty cell in the csv = there's no item/place in that message
    results = []
    for r in rows:
        got = extract(r["text"])
        results.append((r, got["item"] or "", got["location"] or ""))

    item_ok = sum(r["item"] == item for r, item, _ in results)
    place_ok = sum(r["location"] == place for r, _, place in results)
    both_ok = sum(r["item"] == item and r["location"] == place for r, item, place in results)

    def show(item, place):
        return f"{item_name(item) or 'no item'} · {location_name({'location': place}) or 'no place'}"

    return {
        "total": len(rows),
        "item_accuracy": pct(item_ok, len(rows)),
        "location_accuracy": pct(place_ok, len(rows)),
        "exact_match": pct(both_ok, len(rows)),
        "mistakes": [{"text": r["text"], "expected": show(r["item"], r["location"]), "predicted": show(item, place)}
                     for r, item, place in results if (r["item"], r["location"]) != (item, place)],
    }


def faq_metrics(faq, rows):
    results = []
    for r in rows:
        entry, score = faq.search(r["question"])
        results.append((r, entry["topic"] if entry else "none", score))
    correct = sum(r["topic"] == got for r, got, _ in results)
    return {
        "total": len(rows),
        "accuracy": pct(correct, len(rows)),
        "avg_similarity": round(sum(s for _, _, s in results) / len(results), 2) if results else 0,
        "mistakes": [{"text": r["question"], "expected": r["topic"], "predicted": got, "similarity": round(s, 2)}
                     for r, got, s in results if r["topic"] != got],
    }


def live_metrics(logs, threshold):
    # how sure the model was on real messages people typed into the chatbot
    scored = [g for g in logs if g.get("confidence") is not None]
    confs = [g["confidence"] for g in scored]
    counts = Counter(g["intent"] for g in scored).most_common()
    return {
        "messages": len(scored),
        "avg_confidence": pct(sum(confs), len(confs)),
        "low_confidence": pct(sum(c < threshold for c in confs), len(confs)),
        "intents": {"labels": [i for i, _ in counts], "values": [n for _, n in counts]},
    }


@lru_cache(maxsize=1)
def offline_report():
    # the test sets don't change while the site is running, so only score them once
    from .dialogue import MIN_CONFIDENCE, clf, faq
    from .entities import extract
    return {
        "intent": intent_metrics(clf, read_csv("test_intents.csv"), MIN_CONFIDENCE),
        "entities": entity_metrics(extract, read_csv("test_entities.csv")),
        "faq": faq_metrics(faq, read_csv("test_faq.csv")),
    }


def evaluation(logs):
    from .dialogue import MIN_CONFIDENCE
    return {**offline_report(), "live": live_metrics(logs, MIN_CONFIDENCE)}
