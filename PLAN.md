# FindIt — NU Laguna Lost & Found Chatbot

Project plan for turning the Colab prototype into a deployed full-stack web app.

---

## 1. Review of the current notebook

### Bugs (things that are actually broken)

| # | Problem | Example |
|---|---------|---------|
| 1 | **Intent label mismatch.** The dataset uses `REPORT_FOUND`, `SEARCH_ITEM`, `GENERAL_INQUIRY`, but the chatbot only handles `SURRENDER_FOUND`, `REPORT_LOST`, `PROCEDURES`, `GREETING`, `HELP`. Anything the ML model classifies as found/search/inquiry falls through to "I did not understand". | "Someone left a sweater at the gym" → *I'm sorry, I did not understand* |
| 2 | **Substring matching, not word matching.** `"pen" in text` matches inside other words, and the *longest* hit wins even if it's wrong. | "what hap**pen**ed" → PEN · "o**pen** grounds" → PEN · "auto**mobile** keys" → PHONE · "a**cr**oss" → RESTROOM (`cr`) |
| 3 | **Your headline example doesn't work.** "telecommunication device" isn't in the item dictionary. "iPhone" only works by accident (it contains "phone"). "Samsung", "cp", "airpods", "tumbler" in Taglish, etc. all fail. | |
| 4 | **Ambiguous dictionary.** 57 location phrases map to two different places (e.g. `pool` → AQUATICS *and* SWIMMING_POOL, `basketball court` → HOOP_GYM *and* BASKETBALL_COURT). Which one you get depends on sort order, so a lost report and a found report for the same place can fail to match. | |
| 5 | **Global conversation state.** `conversation_state` is one Python dict for the whole server. On the Gradio share link, two students chatting at once overwrite each other's reports. On a real website this is a hard blocker. | |
| 6 | **Data isn't stored.** `surrendered_items` / `lost_reports` are Python lists, so everything is lost when the runtime restarts. | |
| 7 | **Matching is too strict.** It needs an exact item, location **and date**. An item lost Monday and found Tuesday never matches, and neither does one lost in the "gym" and found at the "hoop gym". | |
| 8 | **No way out of a flow.** Once you're in a report, there's no "cancel", and the menu buttons (`1/2/3`) are treated as slot answers. The `PROCEDURES` branch inside the active-conversation block can never be reached. | |
| 9 | **Rules override ML in bad ways.** The `"help"` rule catches "can you **help** me find my wallet" and returns the help menu instead of starting a lost report. Rules run first, so the classifier rarely gets used. | |
| 10 | **Room number fallback is dead code.** It always returns `CLASSROOM` if that label exists, so "Room 203" loses the room number. | |
| 11 | Hard-coded "**1** match found" even when there are several. "Tomorrow" is accepted as a date an item was lost. Time is *required*, even though people usually don't know it. | |

### The accuracy number is misleading

- The notebook trains and tests on `FindIt_intent_dataset.csv`, which is **template-generated** ("I found a X near the Y"). The 30% test split has the same templates as the training data, which is why it shows **99.5%**.
- `dataset.csv` (1,608 more varied rows with typos and Taglish) is downloaded but **never used**.
- Testing the same model on `dataset.csv`:

  | Intent | Recall |
  |---|---|
  | REPORT_FOUND | 0.99 |
  | REPORT_LOST | **0.43** |
  | SEARCH_ITEM | 0.59 |
  | GENERAL_INQUIRY | 0.55 |
  | **Overall accuracy** | **0.636** |

- Merging both files and cross-validating gives ~99.9% again, so `dataset.csv` looks partly generated too. A believable number needs a small **hand-written test set** (100–150 real-style messages from classmates) that is never trained on. That also makes a good NLP-class talking point.

### Code quality

- The slot-filling block (detect → fill → list missing fields → ask) is copy-pasted **4 times**.
- About 800 lines of `!important` CSS fighting Gradio's layout.
- Bare `except:` everywhere hides real errors.
- Every entity lookup loops over the whole DataFrame with `iterrows()`, the slowest way to do it.

---

## 2. Target architecture (Python version)

```
          ┌──────────────────────── Vercel (free) ─────────────────────────┐
 Phone /  │  public/  plain HTML + CSS + JavaScript                        │
 iPad /   │   ├─ index.html   chat UI                                      │
 Desktop ─┼─► └─ admin.html   dashboard (login required, Chart.js)         │
          │                                                                │
          │  api/index.py  Flask app (Python serverless function)          │
          │   ├─ POST /api/chat     NLP + dialogue manager (findit/)       │
          │   └─ GET  /api/stats    numbers for the dashboard              │
          │         │  loads data/model.json, items.csv, locations.csv     │
          └─────────┼──────────────────────────────────────────────────────┘
                    ▼
          Supabase (free): Postgres DB + Auth (admin login)

 ml/train.py (your laptop or Colab): trains with scikit-learn -> data/model.json
```

### Why this stack
- **Python/Flask backend.** All the NLP stays in Python, which is what the class is about. Flask is small: one file of routes.
- **Plain HTML/CSS/JS frontend.** You already know these, so there's no React build step. The chat page is one HTML file, one CSS file and one JS file that calls `/api/chat` with `fetch()`.
- **Vercel runs Flask** as a Python serverless function, so it's free and deploys on every `git push`.
- **scikit-learn is only used for training.** It's too big and slow to load on Vercel's free tier, so the trained model is exported to `data/model.json` and `findit/classifier.py` does the prediction math in plain Python. `tests/test_classifier.py` checks the results match scikit-learn to 3 decimal places.
- **Supabase** provides a real Postgres database, a login system for admins, and a table editor in the browser. Flask talks to it through its REST API.
- **Alternatives considered:**
  - Next.js: more to learn.
  - Gradio/Streamlit on Hugging Face: easy, but hard to customize and looks less "full stack".
  - Django or FastAPI on Render: the free tier sleeps, so the first message takes about 30 seconds.

### Lost & found office
Items are handled by the **Disciplinary Office (near the dugout)**. The FAQ answers, the "where do I bring it" replies, and the matching messages all point there.

## 3. How the chatbot works (the logic)

Each message goes through the same pipeline. The server is **stateless**: the browser sends the conversation state with each message, so users never share state (fixes bug #5).

```
message ─► 1. normalize ─► 2. intent ─► 3. entities ─► 4. dialogue manager ─► 5. action ─► reply
```

### Step 1: Normalize
- Lowercase and strip extra punctuation.
- Replace slang and Taglish with standard words using a small lookup table: `cp → phone`, `naiwan / nawala → lost`, `napulot / nakita ko → found`, `cr → restroom` (whole word only), `kanina → today`.

### Step 2: Intent classification (hybrid)
1. **Buttons and chips** send an explicit action (`{action: "REPORT_LOST"}`), not text, so they're never misclassified.
2. **Control words** are exact rules: `cancel`, `start over`, `yes`, `no`, `edit`.
3. **TF-IDF + Logistic Regression** is used for everything else. The model returns probabilities, not just a label:
   - confidence ≥ 0.55 → use the intent
   - otherwise → ask a clarifying question: *"Did you lose something, or did you find something?"* with two chips.
4. Intents: `REPORT_LOST`, `REPORT_FOUND`, `SEARCH_ITEM`, `GENERAL_INQUIRY`, `GREETING`, `THANKS`. The code uses the **same label names as the dataset** (fixes bug #1).
5. Each message is logged with its predicted intent and confidence, so the admin can see messages the bot was unsure about and add them to the training data.

### Step 3: Entity extraction
| Entity | How |
|---|---|
| **Item** | Match whole words or phrases against the dictionary (regex `\b...\b`, longest phrase first). Then use **fuzzy matching** (edit distance ≤ 1 for words ≤ 5 letters, ≤ 2 for longer) to catch typos like "calcultor" and "umbrela". Add **brand and model names** as synonyms (`iphone, samsung, oppo, vivo, realme, airpods, jbl, hydro flask, aquaflask...`) and generic terms (`telecommunication device, gadget → ask "what kind of device?"`). |
| **Color / brand / description** | Small color word list plus the brand list. This is stored with the report and helps tell two black phones apart. |
| **Location** | Same word-boundary + fuzzy matching. Clean the dictionary so **each phrase maps to exactly one place**. Group places into **zones** (e.g. `HOOP_GYM`, `HIGH_PERFORMANCE_GYM`, `MULTI_PURPOSE_GYM` → zone `GYMS`) so matching can give partial credit. Keep room numbers ("Room 203"). |
| **Date** | today / yesterday / kanina / "last Monday" / "2 days ago" / "Sept 20" / "9/20". Reject future dates. |
| **Time** | "3pm", "15:00", "this morning", "after lunch" → time range. **Optional.** |

### Step 4: Dialogue manager (a small state machine)

```
            ┌────────────── cancel (from any state) ──────────────┐
            ▼                                                      │
  IDLE ──intent──► COLLECTING ──all required slots──► CONFIRMING ──yes──► SAVED ─► IDLE
                   │  ask ONE missing slot at a time     │
                   │  (with chips: "Library", "Gym"...)  └──edit──► COLLECTING
```

- **State** = `{ intent, slots: {item, color, brand, location, date, time, description, contact}, awaiting, step }`
- **Required slots:** item, location, date. **Optional:** time, color, description, contact email (lost reports only, for notifications).
- Every message is still run through entity extraction, so users can answer out of order ("it's black, I lost it at the library").
- **CONFIRMING** shows a **report card** in the chat, with the item icon, location, date and description plus *Confirm* and *Edit* buttons, so nothing gets saved wrong.
- A single `handleSlotFilling()` function replaces the 4 copies.

### Step 5: Actions
| Intent | Action |
|---|---|
| `REPORT_FOUND` | Save to `found_items` with status `pending_surrender` and generate a reference code (`F-2409-0012`). Tell the user to bring the item to the Disciplinary Office near the dugout. **Check open lost reports** for matches and flag them for the admin. |
| `REPORT_LOST` | Save to `lost_reports` with a reference code (`L-2409-0031`), then run **matching** against found items. |
| `SEARCH_ITEM` | Run matching without creating a report, and offer to file one if nothing is found. |
| `GENERAL_INQUIRY` | **FAQ retrieval:** TF-IDF cosine similarity between the question and ~20 FAQ entries (office hours, where the Disciplinary Office is, how long items are kept, what ID to bring). Return the best answer if similarity > threshold, otherwise the office contact. This is a second NLP technique for the class. |

### Matching score (lost report ↔ found item)
```
score = 0
item category equal                   → required (otherwise skip)
same location                         → +40
same zone (e.g. both gyms)            → +20
found_date within 0–1 day of lost     → +30
found_date within 2–7 days            → +15
found before lost date                → skip (impossible)
color matches                         → +20
brand matches                         → +20
description word overlap (TF-IDF cos) → +0..10
show top 3 with score ≥ 40
```
**Privacy:** show the user only partial details ("A black PHONE was turned in near the Gym on Sept 24, ref F-2409-0012. Bring your school ID to the Disciplinary Office near the dugout to verify."). Don't show brand, contents or marks, so people can't claim items that aren't theirs. the Disciplinary Office verifies in person.

---

## 4. Database (Supabase / Postgres)

```sql
found_items (
  id uuid pk, ref_code text unique,
  item text, color text, brand text, description text,
  location text, zone text, date_found date, time_found text,
  finder_contact text null,
  status text check (status in ('pending_surrender','in_custody','claimed','disposed')),
  created_at timestamptz default now(), claimed_at timestamptz null
)

lost_reports (
  id uuid pk, ref_code text unique,
  item text, color text, brand text, description text,
  location text, zone text, date_lost date, time_lost text,
  owner_contact text null,
  status text check (status in ('open','matched','returned','closed')),
  created_at timestamptz default now(), resolved_at timestamptz null
)

matches (
  id uuid pk, lost_id uuid fk, found_id uuid fk,
  score int, status text check (status in ('suggested','confirmed','rejected')),
  created_at timestamptz default now()
)

chat_logs (
  id bigserial pk, session_id text, message text,
  intent text, confidence real, created_at timestamptz default now()
)
```
- **Row Level Security** is on. The public can't read tables directly: the chat API writes with a server-side key, and only logged-in admins can read.
- Admin accounts use Supabase Auth (email + password). Only people whose email is listed in an `admins` table get dashboard access.

---

## 5. Admin dashboard (`/admin`)

- **KPI tiles:** open lost reports · items in custody · items returned (this month) · **return rate** (returned ÷ lost) · average days to return
- **Charts:** reports per week (lost vs found), top item categories, **location hotspots** (where things get lost most), status breakdown
- **Tables:** found items and lost reports with filters and search. Change status (e.g. mark *In custody* when the item is physically surrendered, or *Claimed* when the owner picks it up). Suggested matches can be confirmed or rejected.
- **NLP monitor:** list of low-confidence messages (for retraining) and intent distribution.
- Export to CSV.

---

## 6. UI / UX (modern AI-chat style, with an NU twist)

**Borrowed from modern AI chat apps:** a warm off-white background, one centered conversation column (~720px), a large rounded composer box, a serif font for headings, a collapsible left sidebar, no bubbles for bot messages (just text), and user messages in a soft rounded pill.

**What's unique to FindIt:**
- **NU colors as accents:** navy `#1B2A6B` and gold `#F2C230` (sparingly: send button, reference codes, active states) on warm neutrals.
- **Report cards inside the chat:** structured cards with an item icon, fields, and Confirm/Edit buttons.
- **Claim-stub reference codes** styled like a torn ticket, with a *Copy* button.
- **Suggestion chips** under the composer that change with context ("Library", "Gym", "Today", "Yesterday").
- **Empty-state home screen:** "What did you lose or find today?" with three big action cards.
- Dark mode.

**Responsive layout:**
| Width | Layout |
|---|---|
| Phone (< 640px) | Sidebar becomes a slide-in drawer (hamburger). The composer sticks to the bottom and respects the iPhone home bar (`env(safe-area-inset-bottom)`). Uses `100dvh` so the mobile keyboard doesn't break the layout, with 44px minimum tap targets. |
| iPad (640–1024px) | Collapsible sidebar (icon rail). The chat column fills the width with padding. |
| Desktop | Full sidebar and centered chat column. |

---

## 7. Folder structure

```
lostandfound-chatbot/
├─ findit/                    # the chatbot brain (pure python, no sklearn)
│  ├─ text.py                 # normalize, tokenize, edit distance
│  ├─ classifier.py           # tf-idf + logistic regression inference
│  ├─ entities.py             # item, brand, color, location, room, floor
│  ├─ dates.py                # "kahapon", "last monday", "sept 20", "3pm"
│  ├─ dialogue.py             # state machine            (phase 3)
│  ├─ matching.py             # lost <-> found scoring   (phase 5)
│  └─ faq.py                  # faq retrieval            (phase 3)
├─ data/                      # what the app loads at runtime
│  ├─ model.json              # exported by ml/train.py
│  ├─ items.csv
│  ├─ locations.csv
│  └─ faq.csv                 (phase 3)
├─ ml/
│  ├─ data/                   # training csvs + handwritten test set
│  ├─ train.py
│  └─ requirements.txt
├─ api/index.py               # flask app for vercel     (phase 3)
├─ public/                    # html/css/js              (phase 4)
├─ supabase/schema.sql        # (phase 5)
├─ tests/
└─ README.md
```

## 8. Build phases

| Phase | What | Output |
|---|---|---|
| 0 | GitHub repo, Supabase project, Vercel project | "Hello world" deployed |
| 1 ✅ | **ML pipeline:** merge datasets, clean dictionaries, hand-written test set, train, honest evaluation, export `model.json` | 94.7% on handwritten test (was 71.1%) |
| 2 ✅ | **NLP engine in Python:** normalize, classifier (parity test vs sklearn), entities (word-boundary + fuzzy), dates | 56 tests passing |
| 3 ✅ | **Dialogue manager + FAQ + Flask `/api/chat`** | 68 tests passing |
| 4 ✅ | **Chat UI** (responsive, report cards, chips, dark mode, NLP details panel) | Works locally on desktop, iPad and phone |
| 5 ✅ | **Database + matching** + reference codes | Reports saved in Supabase and matched |
| 6 ✅ | **Admin dashboard + auth** (donut charts, claimed status, Supabase login) | 73 tests passing |
| 7 | **Polish:** rate limiting, input validation, GitHub Actions CI (tests on push), README with screenshots and GIF | Resume-ready |

---

## 9. What makes it count as "full stack" on a resume

- **Frontend:** HTML/CSS/JavaScript, responsive, accessible
- **Backend:** API routes, validation, business logic (dialogue manager, matching)
- **Database:** relational schema, migrations, row-level security
- **Auth:** protected admin area
- **ML/NLP:** a training pipeline in Python and a model served in production, with an honest evaluation
- **DevOps:** CI tests, deployment on Vercel, environment variables and secrets handled properly
- **Docs:** a README with an architecture diagram, screenshots, a live demo link, and a test/admin account for recruiters

---

## 10. Team

Built by Mohammad Balmeh and Shervin Gutierrez for the NLP elective. Add Shervin's GitHub link to the README once he has an account, and describe it on both resumes as a two-person project, including who did which part.
