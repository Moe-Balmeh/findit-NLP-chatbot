# scores how likely a lost report and a found item are the same thing
# (item type, place, date, color, brand). this is the part that actually
# gets people their stuff back.

from datetime import date

MIN_SCORE = 40


def score(lost, found):
    # returns (points, reasons) or None if it can't be the same item
    if not lost.get("item") or lost["item"] == "OTHER" or lost["item"] != found.get("item"):
        return None

    points = 0
    reasons = []

    if lost.get("location") and lost["location"] == found.get("location"):
        points += 40
        reasons.append("same place")
    elif lost.get("zone") and lost["zone"] == found.get("zone"):
        points += 20
        reasons.append("nearby area")

    if valid_date(lost.get("date")) and valid_date(found.get("date")):
        days = (date.fromisoformat(found["date"]) - date.fromisoformat(lost["date"])).days
        # can't be found before it was lost (1 day slack in case they got the date wrong)
        if days < -1 or days > 60:
            return None
        if days <= 1:
            points += 30
            reasons.append("same day")
        elif days <= 7:
            points += 15
            reasons.append("within a week")

    for field in ("color", "brand"):
        a, b = lost.get(field), found.get(field)
        if a and b:
            if a == b:
                points += 20
                reasons.append(f"same {field}")
            else:
                points -= 20

    return points, reasons


def valid_date(value):
    return bool(value) and value != "unknown"


def find_matches(lost, found_items, min_score=MIN_SCORE, limit=3):
    results = []
    for found in found_items:
        s = score(lost, found)
        if s and s[0] >= min_score:
            results.append({"record": found, "score": s[0], "reasons": s[1]})
    return sorted(results, key=lambda r: r["score"], reverse=True)[:limit]


def find_owners(found, lost_reports, min_score=MIN_SCORE, limit=3):
    results = []
    for lost in lost_reports:
        s = score(lost, found)
        if s and s[0] >= min_score:
            results.append({"record": lost, "score": s[0], "reasons": s[1]})
    return sorted(results, key=lambda r: r["score"], reverse=True)[:limit]
