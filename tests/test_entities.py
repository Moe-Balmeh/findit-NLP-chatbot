# tests for items, places, typos, dates and times, including bugs from the old
# notebook (like "what happened" being detected as a pen).

from datetime import date

import pytest

from findit.dates import parse_date, parse_time
from findit.entities import extract

# a saturday, so weekday tests are predictable
TODAY = date(2026, 9, 26)


@pytest.mark.parametrize("text,item", [
    ("i found a telecommunication device inside the gym", "PHONE"),
    ("I found an iPhone inside the gym", "PHONE"),
    ("i lost my automobile keys", "KEYS"),
    ("i lost my walet", "WALLET"),
    ("can u check my carger", "CHARGER"),
    ("can u check my noteobok", "NOTEBOOK"),
    ("i lost my flash driev", "USB_DRIVE"),
    ("my samsung tablet is missing", "TABLET"),
    ("lost my iphone charger", "CHARGER"),
    ("naiwan ko yung payong ko", "UMBRELLA"),
    ("my aquaflask is gone", "WATER_BOTTLE"),
    ("I'd like to report something", None),
])
def test_items(text, item):
    assert extract(text, TODAY)["item"] == item


@pytest.mark.parametrize("text", [
    "what happened to my stuff",
    "i was in the open grounds",
    "i walked across the hallway",
])
def test_no_false_items(text):
    assert extract(text, TODAY)["item"] is None


@pytest.mark.parametrize("text", [
    "may nakita akong wallet sa cr",
    "can i see the list of found items",
    "can i report on behalf of my friend?",
])
def test_typo_fix_leaves_real_words_alone(text):
    e = extract(text, TODAY)
    assert e["brand"] is None
    assert e["location"] in (None, "RESTROOM")


@pytest.mark.parametrize("text,location", [
    ("i lost it in the gym", "GYM"),
    ("at the hoops gym", "HOOP_GYM"),
    ("i found it at the open grounds", "OPEN_GROUNDS"),
    ("sa cr sa 2nd floor", "RESTROOM"),
    ("near the dugout", "DUGOUT"),
    ("found a ball at the basketball court", "HOOP_GYM"),
    ("i left it at the swimming pool", "AQUATICS_CENTER"),
    ("walked across the lobby", "LOBBY"),
])
def test_locations(text, location):
    assert extract(text, TODAY)["location"] == location


def test_ball_on_court_is_still_an_item():
    e = extract("found a ball at the basketball court", TODAY)
    assert e["item"] == "BALL"


def test_room_and_floor():
    e = extract("i left my bag in room 305 on the 3rd floor", TODAY)
    assert e["room"] == "305"
    assert e["floor"] == 3
    assert e["location"] == "CLASSROOM"


def test_brand_and_color():
    e = extract("has a blue hydro flask been turned in?", TODAY)
    assert e["item"] == "WATER_BOTTLE"
    assert e["brand"] == "Hydro Flask"
    assert e["color"] == "blue"


@pytest.mark.parametrize("text,expected", [
    ("i lost it today", date(2026, 9, 26)),
    ("kanina lang", date(2026, 9, 26)),
    ("yesterday afternoon", date(2026, 9, 25)),
    ("kahapon", date(2026, 9, 25)),
    ("3 days ago", date(2026, 9, 23)),
    ("two days ago", date(2026, 9, 24)),
    ("tatlong araw na ang nakalipas", date(2026, 9, 23)),
    ("last monday", date(2026, 9, 21)),
    ("last saturday", date(2026, 9, 19)),
    ("on sept 20", date(2026, 9, 20)),
    ("september 20, 2026", date(2026, 9, 20)),
    ("9/20", date(2026, 9, 20)),
    ("dec 20", date(2025, 12, 20)),
    ("tomorrow", None),
    ("may nakita akong wallet", None),
])
def test_dates(text, expected):
    assert parse_date(text, TODAY) == expected


@pytest.mark.parametrize("text,expected", [
    ("around 3pm", "3:00 PM"),
    ("at 3:30 pm", "3:30 PM"),
    ("15:45", "3:45 PM"),
    ("this morning", "Morning"),
    ("after lunch", "Afternoon"),
    ("i lost my iphone 13", None),
])
def test_times(text, expected):
    assert parse_time(text) == expected
