# trains the intent classifier with scikit-learn, tests it on our handwritten
# messages (the honest accuracy number) and exports the weights to data/model.json.
# run it again whenever the training data changes.

import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import FeatureUnion, Pipeline

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from findit.text import normalize  # noqa: E402

DATA = ROOT / "ml" / "data"
TRAIN_FILES = ["FindIt_intent_dataset.csv", "dataset.csv", "extra_training.csv"]
OUT = ROOT / "data" / "model.json"


def load_training():
    frames = [pd.read_csv(DATA / f)[["text", "intent"]] for f in TRAIN_FILES]
    df = pd.concat(frames).dropna()
    df["text"] = df["text"].map(normalize)
    before = len(df)
    df = df.drop_duplicates("text")
    print(f"training rows: {len(df)} ({before - len(df)} duplicates dropped)")
    print(df["intent"].value_counts().to_string(), "\n")
    return df


def build_model():
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        # char n-grams inside words make it robust to typos like "walet"
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5),
                                 sublinear_tf=True, min_df=2)),
    ])
    clf = LogisticRegression(C=5, max_iter=5000, class_weight="balanced")
    return Pipeline([("features", features), ("clf", clf)])


def export(model, path):
    clf = model.named_steps["clf"]
    blocks = []
    offset = 0
    for name, vec in model.named_steps["features"].transformer_list:
        vocab = vec.vocabulary_
        feats = {}
        for term, idx in vocab.items():
            col = offset + idx
            feats[term] = [round(float(vec.idf_[idx]), 6)] + [
                round(float(clf.coef_[k, col]), 6) for k in range(len(clf.classes_))
            ]
        blocks.append({
            "analyzer": vec.analyzer,
            "ngram_range": list(vec.ngram_range),
            "features": feats,
        })
        offset += len(vocab)

    model_json = {
        "classes": clf.classes_.tolist(),
        "intercept": [round(float(b), 6) for b in clf.intercept_],
        "blocks": blocks,
    }
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model_json, f, separators=(",", ":"))
    print(f"\nexported {offset} features -> {path} ({path.stat().st_size // 1024} KB)")


def main():
    df = load_training()
    X, y = df["text"].tolist(), df["intent"].tolist()

    # heads up: this number is inflated, the training csvs are mostly templates
    cv = StratifiedKFold(5, shuffle=True, random_state=42)
    cv_acc = cross_val_score(build_model(), X, y, cv=cv).mean()
    print(f"5-fold cv accuracy (templated data): {cv_acc:.3f}")

    model = build_model()
    model.fit(X, y)

    # the real test: handwritten messages the model never sees in training
    test = pd.read_csv(DATA / "test_handwritten.csv")
    X_test = test["text"].map(normalize).tolist()
    y_test = test["intent"].tolist()
    pred = model.predict(X_test)

    print(f"handwritten test accuracy: {accuracy_score(y_test, pred):.3f}\n")
    print(classification_report(y_test, pred, digits=3))
    labels = model.named_steps["clf"].classes_
    cm = pd.DataFrame(confusion_matrix(y_test, pred, labels=labels),
                      index=labels, columns=labels)
    print("confusion matrix (rows = true, cols = predicted)")
    print(cm.to_string())

    wrong = [(t, p, s) for s, t, p in zip(test["text"], y_test, pred) if t != p]
    if wrong:
        print("\nmistakes:")
        for t, p, s in wrong:
            print(f"  {t:16s} -> {p:16s} {s}")

    export(model, OUT)
    save_parity_fixture(model, X_test + X[:200])


def save_parity_fixture(model, texts):
    # sklearn's own probabilities, so tests can check findit/classifier.py matches
    probs = model.predict_proba(texts)
    classes = model.named_steps["clf"].classes_.tolist()
    rows = [{"text": t, "probs": dict(zip(classes, p.round(6).tolist()))}
            for t, p in zip(texts, probs)]
    path = ROOT / "tests" / "fixtures" / "parity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
