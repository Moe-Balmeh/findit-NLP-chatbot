# entity extraction: pulls out the item, brand, color, place, room, floor, date
# and time using our word lists in data/. this is how "i found an iphone in the gym"
# becomes item=PHONE, location=GYM.

import csv
import re
from pathlib import Path

from .dates import parse_date, parse_time
from .text import COMMON_WORDS, edit_distance, normalize, tokenize

DATA = Path(__file__).resolve().parent.parent / "data"

COLORS = {"black": "black", "itim": "black", "white": "white", "puti": "white",
          "gray": "gray", "grey": "gray", "silver": "silver", "gold": "gold",
          "red": "red", "pula": "red", "maroon": "maroon", "blue": "blue", "asul": "blue",
          "navy": "navy blue", "green": "green", "berde": "green", "yellow": "yellow",
          "dilaw": "yellow", "orange": "orange", "pink": "pink", "purple": "purple",
          "violet": "purple", "brown": "brown", "beige": "beige"}


def load_terms(filename, col1, col2):
    # {("hydro", "flask"): ("WATER_BOTTLE", "Hydro Flask"), ...}
    terms = {}
    with open(DATA / filename, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            terms[tuple(tokenize(row["term"]))] = (row[col1] or None, row[col2] or None)
    return terms


ITEMS = load_terms("items.csv", "item", "brand")
LOCATIONS = load_terms("locations.csv", "location", "zone")
KNOWN_WORDS = {w for term in list(ITEMS) + list(LOCATIONS) for w in term}


def fix_typo(word):
    # "walet" -> "wallet", but leave real words and short words alone
    if word in KNOWN_WORDS or word in COMMON_WORDS or word.isdigit() or len(word) < 3:
        return word
    max_dist = 1 if len(word) <= 6 else 2
    candidates = [w for w in KNOWN_WORDS
                  if len(w) >= 4 and w[0] == word[0] and abs(len(w) - len(word)) <= max_dist]
    scored = sorted((edit_distance(word, w), w) for w in candidates)
    if not scored or scored[0][0] > max_dist:
        return word
    # two equally close words means we can't tell which one they meant
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return word
    return scored[0][1]


def find_terms(words, terms, skip=()):
    # longest phrase first, so "phone charger" wins over "phone"
    found = []
    used = set(skip)
    for size in range(4, 0, -1):
        for i in range(len(words) - size + 1):
            span = set(range(i, i + size))
            phrase = tuple(words[i:i + size])
            if phrase in terms and not span & used:
                found.append((i, span, terms[phrase]))
                used |= span
    found.sort(key=lambda x: x[0])
    return found


def extract(text, today=None):
    words = [fix_typo(w) for w in tokenize(text)]
    t = normalize(text)

    # places first so "basketball court" isn't read as a ball
    places = find_terms(words, LOCATIONS)
    place_words = set().union(*[span for _, span, _ in places])
    items = find_terms(words, ITEMS, skip=place_words)

    # "samsung tablet": the item word wins, the brand just becomes the brand
    plain = [v[0] for _, _, v in items if v[0] and not v[1]]
    branded = [v[0] for _, _, v in items if v[0] and v[1]]
    item_list = list(dict.fromkeys(plain + branded))
    brands = [v[1] for _, _, v in items if v[1]]

    location, zone = places[0][2] if places else (None, None)

    room = re.search(r"\b(?:room|rm)\s*#?\s*(\d{2,4}[a-z]?)\b", t)
    if room and not location:
        location, zone = "CLASSROOM", "ACADEMIC"

    floor = re.search(r"\b(\d)(?:st|nd|rd|th)? ?(?:floor|flr)\b", t)

    return {
        "item": item_list[0] if item_list else None,
        "items": item_list,
        "brand": brands[0] if brands else None,
        "color": next((COLORS[w] for w in words if w in COLORS), None),
        "location": location,
        "zone": zone,
        "room": room.group(1).upper() if room else None,
        "floor": int(floor.group(1)) if floor else None,
        "date": parse_date(t, today),
        "time": parse_time(t),
    }
