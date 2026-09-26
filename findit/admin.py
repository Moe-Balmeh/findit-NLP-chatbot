# builds everything the admin dashboard shows: the summary numbers, the data for
# the circle charts, and the tables of found items and lost reports.
# the office uses this page to see what's going on and mark items as claimed.

from collections import Counter

from .labels import date_name, item_name, location_name

FOUND_STATUS = {"pending_surrender": "Waiting for drop-off", "in_custody": "At the office",
                "claimed": "Claimed", "disposed": "Disposed"}
LOST_STATUS = {"open": "Open", "matched": "Matched", "returned": "Returned", "closed": "Closed"}


def top_counts(values, limit=5):
    # biggest few slices, everything else goes into "Other" so the chart stays readable
    counts = Counter(v for v in values if v).most_common()
    top = counts[:limit]
    rest = sum(c for _, c in counts[limit:])
    if rest:
        top.append(("Other", rest))
    return {"labels": [label for label, _ in top], "values": [c for _, c in top]}


def row(rec, other_refs):
    return {
        "id": rec["id"],
        "ref_code": rec["ref_code"],
        "item": item_name(rec["item"]),
        "details": ", ".join(x for x in (rec.get("color"), rec.get("brand"), rec.get("description")) if x),
        "location": location_name(rec),
        "date": date_name(rec.get("date")),
        "status": rec["status"],
        "matches": other_refs,
    }


def dashboard(found, lost, matches):
    found_ref = {f["id"]: f["ref_code"] for f in found}
    lost_ref = {r["id"]: r["ref_code"] for r in lost}
    # which reports might belong together, shown next to each row
    found_matches, lost_matches = {}, {}
    for m in matches:
        if m["found_id"] in found_ref and m["lost_id"] in lost_ref:
            found_matches.setdefault(m["found_id"], []).append(lost_ref[m["lost_id"]])
            lost_matches.setdefault(m["lost_id"], []).append(found_ref[m["found_id"]])

    claimed = sum(1 for f in found if f["status"] == "claimed")
    status_counts = Counter(f["status"] for f in found)

    return {
        "summary": {
            "lost": len(lost),
            "found": len(found),
            "claimed": claimed,
            "return_rate": round(100 * claimed / len(found)) if found else 0,
        },
        "charts": {
            "status": {"labels": [FOUND_STATUS[s] for s in FOUND_STATUS if status_counts[s]],
                       "values": [status_counts[s] for s in FOUND_STATUS if status_counts[s]]},
            "items": top_counts(item_name(r["item"]) for r in found + lost),
            "places": top_counts(location_name(r) for r in found + lost if r.get("location")),
        },
        "found": [row(f, found_matches.get(f["id"], [])) for f in found],
        "lost": [row(r, lost_matches.get(r["id"], [])) for r in lost],
        "found_status": FOUND_STATUS,
        "lost_status": LOST_STATUS,
    }
