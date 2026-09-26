# answers general questions like "where is the lost and found?" by finding the most
# similar question in data/faq.csv (tf-idf + cosine similarity).

import csv
import math
from collections import Counter
from pathlib import Path

from .text import tokenize

FAQ_PATH = Path(__file__).resolve().parent.parent / "data" / "faq.csv"
STOPWORDS = set("a an the to of is are am be do does did i my me it this that for in on at "
                "can you your please po ba yung ang ng sa na ko ako".split())


def words(text):
    w = [t for t in tokenize(text) if t not in STOPWORDS]
    return w + [f"{a} {b}" for a, b in zip(w, w[1:])]  # words + bigrams


class FAQ:
    def __init__(self, path=FAQ_PATH):
        # every example question becomes its own tf-idf vector
        self.questions = []
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                entry = {"topic": row["topic"], "answer": row["answer"].replace("\\n", "\n")}
                for q in row["questions"].split("|"):
                    self.questions.append((entry, Counter(words(q))))

        doc_freq = Counter()
        for _, counts in self.questions:
            doc_freq.update(counts.keys())
        n = len(self.questions)
        self.idf = {t: math.log((1 + n) / (1 + df)) + 1 for t, df in doc_freq.items()}
        self.questions = [(entry, self.vector(counts)) for entry, counts in self.questions]

    def vector(self, counts):
        vec = {t: (1 + math.log(c)) * self.idf.get(t, 0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1
        return {t: v / norm for t, v in vec.items()}

    def search(self, text):
        # cosine similarity against every example question, return the best one
        query = self.vector(Counter(words(text)))
        best, best_score = None, 0.0
        for entry, vec in self.questions:
            sim = sum(w * vec.get(t, 0) for t, w in query.items())
            if sim > best_score:
                best, best_score = entry, sim
        return best, best_score
