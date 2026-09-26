# turns date and time words into real dates ("kahapon", "3 days ago", "sept 20", "3pm").
# matching needs actual dates to compare when something was lost vs found.

import re
from datetime import date, datetime, timedelta, timezone

from .text import normalize

PH_TZ = timezone(timedelta(hours=8))  # no daylight saving in the philippines

WEEKDAYS = {"monday": 0, "lunes": 0, "tuesday": 1, "martes": 1, "wednesday": 2,
            "miyerkules": 2, "thursday": 3, "huwebes": 3, "friday": 4, "biyernes": 4,
            "saturday": 5, "sabado": 5, "sunday": 6, "linggo": 6}
NUMBER_WORDS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "isang": 1, "dalawang": 2, "tatlong": 3}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_RE = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
            r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")


def today_ph():
    return datetime.now(PH_TZ).date()


def parse_date(text, today=None):
    today = today or today_ph()
    t = normalize(text)

    if re.search(r"\b(yesterday|kahapon|last night)\b", t):
        return today - timedelta(days=1)
    if re.search(r"\b(today|kanina|ngayon|this morning|this afternoon|earlier)\b", t):
        return today

    # "3 days ago", "two days ago", "3 araw na ang nakalipas"
    m = re.search(r"\b(\d+|a|one|two|three|four|five|six|seven|isang|dalawang|tatlong)\s+"
                  r"(?:days?|araw)\s+(?:ago|na ang nakalipas|nakaraan)\b", t)
    if m:
        n = m.group(1)
        return today - timedelta(days=int(n) if n.isdigit() else NUMBER_WORDS[n])

    # "last monday", "nung lunes" -> most recent one
    m = re.search(r"\b(last )?(" + "|".join(WEEKDAYS) + r")\b", t)
    if m:
        days_back = (today.weekday() - WEEKDAYS[m.group(2)]) % 7
        if days_back == 0 and m.group(1):
            days_back = 7
        return today - timedelta(days=days_back)

    # "sept 20" / "september 20, 2026"
    m = re.search(r"\b" + MONTH_RE + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s*(20\d\d))?", t)
    if m:
        return make_date(m.group(3), MONTHS.index(m.group(1)[:3]) + 1, m.group(2), today)

    # "9/20" or "9/20/2026", month first
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(20\d\d))?\b", t)
    if m:
        return make_date(m.group(3), m.group(1), m.group(2), today)

    return None


def make_date(year, month, day, today):
    try:
        d = date(int(year or today.year), int(month), int(day))
    except ValueError:
        return None
    if d > today:
        # "dec 20" said in january means last year, but a future date with a year is wrong
        return None if year else d.replace(year=d.year - 1)
    return d


def parse_time(text):
    t = normalize(text)

    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1))}:{m.group(2) or '00'} {m.group(3).upper()}"

    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", t)
    if m:
        hour = int(m.group(1))
        return f"{hour % 12 or 12}:{m.group(2)} {'AM' if hour < 12 else 'PM'}"

    for words, label in [("after lunch|afternoon|hapon", "Afternoon"),
                         ("noon|tanghali|lunch", "Around noon"),
                         ("morning|umaga", "Morning"),
                         ("evening|night|gabi", "Evening")]:
        if re.search(rf"\b({words})\b", t):
            return label
    return None
