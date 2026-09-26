# FindIt: NU Laguna Lost & Found Chatbot

A lost and found assistant for NU Laguna. Students and faculty describe what they lost or found in plain English or Taglish, and FindIt records the report and checks it against items that were already turned in.

> Work in progress. See [PLAN.md](PLAN.md) for the roadmap.

## How it works

```
message -> intent classifier -> entity extraction -> dialogue manager -> save + match
           (tf-idf + logreg)    (items, places,      (asks for missing
                                 dates, typos)        info, confirms)
```

- **Intent classification.** TF-IDF (word 1–2 grams plus character 2–5 grams) with logistic regression, trained with scikit-learn. The trained weights are exported to JSON and run in plain Python, so the web server doesn't need scikit-learn.
- **Entity extraction.** Whole-word dictionary matching for 30+ item types and 50+ campus places, typo correction by edit distance ("walet" → wallet), brand names ("iPhone" → phone), Taglish ("payong", "kahapon"), room numbers, floors, dates and times.
- **Dialogue manager.** Asks for whatever is missing one question at a time, lets you answer out of order, and shows a confirm card before saving.
- **Matching.** Scores lost reports against found items by item type, place, nearby area, date gap, color and brand.
- **FAQ.** TF-IDF cosine similarity against common questions.

## Results

| | Accuracy |
|---|---|
| Original notebook model on the handwritten test set | 71.1% |
| Current model on the handwritten test set | **94.7%** |

The handwritten test set is 114 realistic messages the model never trains on. The training data is mostly template-generated, so cross-validation on it (~99%) is not a meaningful number.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # mac/linux: source .venv/bin/activate
pip install -r requirements.txt -r ml/requirements.txt

copy .env.example .env          # then add your supabase url + secret key
                                # (without keys it runs with an in-memory store)

python ml/train.py              # retrain + export data/model.json
python -m pytest                # run tests
python api/index.py             # open http://127.0.0.1:5000
```

## Project structure

```
findit/     chatbot logic (classifier, entities, dates, dialogue, matching, faq)
data/       model.json, item + location dictionaries, faq
ml/         training script and datasets
api/        flask app (deployed on vercel)
public/     html / css / js frontend
supabase/   database schema
tests/      pytest tests
```

## Team

- Mohammad Balmeh
- Shervin Gutierrez

Built for our NLP elective at National University – Laguna.
