# intent classifier: decides if a message is REPORT_LOST, REPORT_FOUND,
# SEARCH_ITEM or GENERAL_INQUIRY. it runs the tf-idf + logistic regression model
# from ml/train.py using plain python math, so the website doesn't need scikit-learn.

import json
import math
import re
from pathlib import Path

from .text import normalize

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "model.json"

# same regexes sklearn uses, so features line up exactly
_WORD = re.compile(r"(?u)\b\w\w+\b")
_MULTI_WS = re.compile(r"\s\s+")


def word_ngrams(text, lo, hi):
    tokens = _WORD.findall(text)
    grams = []
    for n in range(lo, hi + 1):
        for i in range(len(tokens) - n + 1):
            grams.append(" ".join(tokens[i:i + n]))
    return grams


def char_wb_ngrams(text, lo, hi):
    grams = []
    for word in _MULTI_WS.sub(" ", text).split():
        word = f" {word} "
        for n in range(lo, hi + 1):
            offset = 0
            grams.append(word[offset:offset + n])
            while offset + n < len(word):
                offset += 1
                grams.append(word[offset:offset + n])
            if offset == 0:
                break
    return grams


class IntentClassifier:
    def __init__(self, path=MODEL_PATH):
        with open(path, encoding="utf-8") as f:
            model = json.load(f)
        self.classes = model["classes"]
        self.intercept = model["intercept"]
        self.blocks = model["blocks"]

    def _block_scores(self, block, text):
        lo, hi = block["ngram_range"]
        if block["analyzer"] == "word":
            grams = word_ngrams(text, lo, hi)
        else:
            grams = char_wb_ngrams(text, lo, hi)

        counts = {}
        for g in grams:
            if g in block["features"]:
                counts[g] = counts.get(g, 0) + 1

        # sublinear tf * idf, then l2 normalize
        weights = {}
        for g, c in counts.items():
            idf = block["features"][g][0]
            weights[g] = (1 + math.log(c)) * idf
        norm = math.sqrt(sum(w * w for w in weights.values())) or 1.0

        scores = [0.0] * len(self.classes)
        for g, w in weights.items():
            coefs = block["features"][g][1:]
            for k in range(len(scores)):
                scores[k] += (w / norm) * coefs[k]
        return scores

    def predict_proba(self, text):
        text = normalize(text)
        scores = list(self.intercept)
        for block in self.blocks:
            for k, s in enumerate(self._block_scores(block, text)):
                scores[k] += s
        top = max(scores)
        exps = [math.exp(s - top) for s in scores]
        total = sum(exps)
        return {c: e / total for c, e in zip(self.classes, exps)}

    def predict(self, text):
        probs = self.predict_proba(text)
        label = max(probs, key=probs.get)
        return label, probs[label]
