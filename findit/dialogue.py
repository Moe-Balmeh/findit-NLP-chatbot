# the brain of the chatbot. takes a message, uses the classifier and entities to
# understand it, asks for whatever is still missing, then saves the report and
# checks for matches. the conversation state goes back and forth with the browser,
# so every user has their own conversation.

import re
from datetime import timedelta

from .classifier import IntentClassifier
from .dates import today_ph
from .entities import ITEMS, LOCATIONS, extract
from .faq import FAQ
from .labels import date_name, item_name, location_name
from .matching import find_matches, find_owners
from .store import RECORD_FIELDS
from .text import normalize

OFFICE = "Disciplinary Office near the dugout"
MIN_CONFIDENCE = 0.5

FLOWS = ("REPORT_LOST", "REPORT_FOUND", "SEARCH_ITEM")
REQUIRED = {
    "REPORT_LOST": ["item", "location", "date"],
    "REPORT_FOUND": ["item", "location", "date"],
    "SEARCH_ITEM": ["item"],
}
ITEM_CODES = {v[0] for v in ITEMS.values() if v[0]}
ZONE_OF = {loc: zone for loc, zone in LOCATIONS.values()}

GREETING = re.compile(r"^(hi|hello|hey|good (morning|afternoon|evening)|kumusta)\b")
THANKS = re.compile(r"\b(thanks|thank you|ty|salamat)\b")
CANCEL = re.compile(r"^(cancel|stop|never ?mind|start over)\b")
YES = re.compile(r"^(yes|yep|yeah|correct|confirm|ok|okay|sure|oo|opo)\b")
SKIP = re.compile(r"^(skip|none|no|nothing|wala)\b")
UNSURE = re.compile(r"\b(not sure|dont know|don't know|idk|di ko alam|no idea)\b")

MENU = [
    {"label": "I lost something", "action": "REPORT_LOST"},
    {"label": "I found something", "action": "REPORT_FOUND"},
    {"label": "Search found items", "action": "SEARCH_ITEM"},
    {"label": "How it works", "action": "FAQ"},
]
CHIPS = {
    "item": [{"label": l, "action": f"set:item:{c}"} for l, c in [
        ("Phone", "PHONE"), ("Wallet", "WALLET"), ("Student ID", "STUDENT_ID"),
        ("Umbrella", "UMBRELLA"), ("Tumbler", "WATER_BOTTLE"), ("Bag", "BACKPACK")]],
    "location": [{"label": l, "action": f"set:location:{c}"} for l, c in [
        ("Library", "LIBRARY"), ("Gym", "GYM"), ("Cafeteria", "CAFETERIA"),
        ("Classroom", "CLASSROOM"), ("Restroom", "RESTROOM"), ("Hallway", "HALLWAY")]]
        + [{"label": "Not sure", "text": "not sure"}],
    "date": [{"label": "Today", "action": "set:date:today"},
             {"label": "Yesterday", "action": "set:date:yesterday"},
             {"label": "Not sure", "action": "set:date:unknown"}],
    "details": [{"label": "Skip", "action": "skip"}],
}
FAQ_CHIPS = ["Where is the lost and found?", "How do I claim an item?",
             "Is there a fee to claim?", "How does FindIt work?"]

clf = IntentClassifier()
faq = FAQ()


def new_state():
    return {"mode": "idle", "intent": None, "slots": {}, "awaiting": None}


def load_state(raw):
    # the browser sends the state back each time, so only keep what we expect
    state = new_state()
    if not isinstance(raw, dict):
        return state
    if raw.get("mode") in ("collecting", "confirming"):
        state["mode"] = raw["mode"]
    if raw.get("intent") in FLOWS:
        state["intent"] = raw["intent"]
    if raw.get("awaiting") in CHIPS:
        state["awaiting"] = raw["awaiting"]
    if isinstance(raw.get("slots"), dict):
        state["slots"] = {k: v for k, v in raw["slots"].items()
                          if k in RECORD_FIELDS and isinstance(v, (str, int)) and len(str(v)) < 300}
    if state["mode"] != "idle" and not state["intent"]:
        return new_state()
    return state


def respond(state=None, message=None, action=None, store=None, today=None, session_id=None):
    reply = {"messages": [], "chips": [], "nlp": None, "state": load_state(state)}
    today = today or today_ph()
    message = (message or "").strip()[:500]

    if action:
        handle_action(reply, action, store, today)
    elif message:
        handle_message(reply, message, store, today)
        if store is not None:
            store.log(session_id, message, reply["nlp"]["intent"], reply["nlp"]["confidence"])
    else:
        welcome(reply)
    return reply


def say(reply, text):
    reply["messages"].append({"type": "text", "text": text})


def handle_action(reply, action, store, today):
    st = reply["state"]
    # "keep:" starts a flow but keeps what the user already told us
    keep = action.startswith("keep:")
    action = action.removeprefix("keep:")

    if action in FLOWS:
        start_flow(reply, action, st["slots"] if keep else {}, store, today)
    elif action == "FAQ":
        say(reply, "Here are some common questions. You can also just type yours.")
        reply["chips"] = [{"label": q, "text": q} for q in FAQ_CHIPS]
    elif action == "confirm" and st["mode"] == "confirming":
        save(reply, store, today)
    elif action == "edit" and st["mode"] == "confirming":
        say(reply, "Just type what to change, like *\"it was at the gym\"* or *\"it's blue\"*.")
        reply["chips"] = confirm_chips()
    elif action == "skip" and st["awaiting"] == "details":
        st["slots"]["description"] = ""
        next_step(reply, store, today)
    elif action.startswith("set:") and st["mode"] == "collecting":
        _, slot, value = (action.split(":") + ["", ""])[:3]
        slots = st["slots"]
        if slot == "item" and value in ITEM_CODES:
            slots["item"] = value
        elif slot == "location" and value in ZONE_OF:
            slots["location"], slots["zone"] = value, ZONE_OF[value]
        elif slot == "date" and value == "unknown":
            slots["date"] = "unknown"
        elif slot == "date" and value in ("today", "yesterday"):
            days = 0 if value == "today" else 1
            slots["date"] = (today - timedelta(days=days)).isoformat()
        next_step(reply, store, today)
    else:
        welcome(reply)


def handle_message(reply, text, store, today):
    st = reply["state"]
    t = normalize(text)
    new = slots_from(extract(text, today))
    reply["nlp"] = {"method": "rule", "intent": None, "confidence": None,
                    "found": describe(new, today)}

    if CANCEL.match(t):
        reply["nlp"]["intent"] = "CANCEL"
        welcome(reply, "Okay, I cancelled that. What would you like to do?")
        return

    if st["mode"] == "confirming":
        if YES.match(t):
            save(reply, store, today)
        elif update(st["slots"], new):
            show_confirm(reply, today, updated=True)
        else:
            say(reply, "Tap **Confirm** if everything is right, or type what to change.")
            reply["chips"] = confirm_chips()
        return

    if st["mode"] == "collecting":
        # they might ask a question in the middle of a report
        if not new and answer_question(reply, text, min_score=0.5):
            say(reply, "Okay, back to your report.")
            next_step(reply, store, today)
            return
        reply["nlp"].update(method="slot filling", intent="ANSWER:" + (st["awaiting"] or "").upper())
        fill_answer(st, new, text, t)
        next_step(reply, store, today)
        return

    if GREETING.match(t) and not new:
        reply["nlp"]["intent"] = "GREETING"
        welcome(reply, "Hello! I'm **FindIt**, NU Laguna's lost and found assistant. "
                       "What can I help you with?")
        return
    if THANKS.search(t) and not new:
        reply["nlp"]["intent"] = "THANKS"
        say(reply, "You're welcome! Anything else I can help with?")
        reply["chips"] = MENU
        return

    intent, conf = clf.predict(text)
    reply["nlp"].update(method="TF-IDF + logistic regression", intent=intent,
                        confidence=round(conf, 2))

    if conf < MIN_CONFIDENCE:
        if answer_question(reply, text, min_score=0.45):
            return
        if new:
            st["slots"] = new
            say(reply, "Just to be sure, did you **lose** it or **find** it?")
            reply["chips"] = [{"label": "I lost it", "action": "keep:REPORT_LOST"},
                              {"label": "I found it", "action": "keep:REPORT_FOUND"}]
            return
        say(reply, "Sorry, I'm not sure what you mean. Here's what I can help with:")
        reply["chips"] = MENU
    elif intent == "GENERAL_INQUIRY":
        if not answer_question(reply, text, min_score=0.3):
            say(reply, f"I'm not sure about that one. The **{OFFICE}** can help with anything else.")
        reply["chips"] = MENU
    else:
        start_flow(reply, intent, new, store, today)


def slots_from(ents):
    slots = {k: ents[k] for k in ("item", "brand", "color", "location", "zone",
                                  "room", "floor", "time") if ents[k]}
    if ents["date"]:
        slots["date"] = ents["date"].isoformat()
    return slots


def update(slots, new):
    changed = False
    for key, value in new.items():
        if slots.get(key) != value:
            slots[key] = value
            changed = True
    if "location" in new and "room" not in new:
        slots.pop("room", None)
    return changed


def fill_answer(st, new, text, t):
    slots = st["slots"]
    awaiting = st["awaiting"]
    update(slots, new)

    # nothing recognized, so keep what they typed as-is
    if awaiting == "item" and "item" not in new:
        slots["item"] = "OTHER"
        slots["description"] = text[:200]
    elif awaiting == "location" and "location" not in new:
        slots["location"] = "OTHER"
        slots["location_detail"] = "Not sure" if UNSURE.search(t) else text[:120]
    elif awaiting == "date" and "date" not in new and UNSURE.search(t):
        slots["date"] = "unknown"
    elif awaiting == "details":
        slots["description"] = "" if SKIP.match(t) else text[:300]


def answer_question(reply, text, min_score):
    entry, score = faq.search(text)
    if score < min_score:
        return False
    say(reply, entry["answer"])
    if reply["nlp"]:
        reply["nlp"]["faq"] = f"{entry['topic']} ({score:.0%} similar)"
    reply["chips"] = MENU
    return True


def start_flow(reply, intent, slots, store, today):
    st = reply["state"]
    st.update(new_state(), mode="collecting", intent=intent, slots=dict(slots))

    intro = {
        "REPORT_LOST": "Sorry to hear that. Let's get it reported.",
        "REPORT_FOUND": "Thanks for turning it in! Let's record it so the owner can find it.",
        "SEARCH_ITEM": "Sure, let me check what's been turned in.",
    }[intent]
    got = describe(slots, today)
    if intent != "SEARCH_ITEM" and got:
        intro += " Got it: " + " · ".join(f"**{v}**" for v in got.values()) + "."
    say(reply, intro)
    next_step(reply, store, today)


def next_step(reply, store, today):
    st = reply["state"]
    slots = st["slots"]
    st["mode"] = "collecting"

    for slot in REQUIRED[st["intent"]]:
        if not slots.get(slot):
            ask(reply, slot)
            return
    if st["intent"] == "SEARCH_ITEM":
        search(reply, store, today)
    elif "description" not in slots:
        ask(reply, "details")
    else:
        show_confirm(reply, today)


def ask(reply, slot):
    st = reply["state"]
    st["awaiting"] = slot
    found = st["intent"] == "REPORT_FOUND"
    thing = item_name(st["slots"].get("item")).lower() or "item"

    if slot == "item":
        question = {"REPORT_LOST": "What did you lose?", "REPORT_FOUND": "What did you find?",
                    "SEARCH_ITEM": "What item are you looking for?"}[st["intent"]]
    elif slot == "location":
        question = f"Where did you find the {thing}?" if found else f"Where do you think you lost your {thing}?"
    elif slot == "date":
        question = "When did you find it?" if found else "When did you last have it?"
    else:
        question = "Can you describe it? Color, brand, stickers, anything that stands out."
    say(reply, question)
    reply["chips"] = CHIPS[slot]


def report_fields(slots, today):
    desc = slots.get("description") or ""
    # skip color/brand if the description already says it
    details = [x for x in (slots.get("color"), slots.get("brand")) if x and x.lower() not in desc.lower()]
    if desc:
        details.append(desc)
    when = date_name(slots.get("date"), today)
    if slots.get("time"):
        when += f", {slots['time']}"

    fields = [{"icon": "item", "label": "Item", "value": item_name(slots.get("item"))}]
    if details:
        fields.append({"icon": "tag", "label": "Details", "value": ", ".join(details)})
    fields.append({"icon": "pin", "label": "Location", "value": location_name(slots)})
    fields.append({"icon": "calendar", "label": "When", "value": when})
    return fields


def show_confirm(reply, today, updated=False):
    st = reply["state"]
    st["mode"] = "confirming"
    st["awaiting"] = None
    kind = "lost" if st["intent"] == "REPORT_LOST" else "found"
    say(reply, "Updated. How does this look?" if updated else "Here's your report. Does everything look right?")
    reply["messages"].append({"type": "report", "kind": kind,
                              "fields": report_fields(st["slots"], today)})
    reply["chips"] = confirm_chips()


def confirm_chips():
    return [{"label": "Confirm", "action": "confirm"},
            {"label": "Edit", "action": "edit"},
            {"label": "Cancel", "action": "cancel"}]


def match_cards(matches, today):
    items = []
    for m in matches:
        rec = m["record"]
        items.append({
            "item": item_name(rec["item"]),
            "color": rec.get("color"),
            "location": location_name(rec),
            "date": date_name(rec.get("date"), today),
            "ref_code": rec["ref_code"],
            "reasons": m["reasons"],
        })
    return {"type": "matches", "items": items}


def save(reply, store, today):
    st = reply["state"]
    lost = st["intent"] == "REPORT_LOST"
    rec = store.add_lost(st["slots"]) if lost else store.add_found(st["slots"])
    say(reply, "Your report is saved. Keep this reference code:" if lost
        else "Thank you for helping! Your report is saved:")
    reply["messages"].append({"type": "ticket", "kind": "lost" if lost else "found",
                              "ref_code": rec["ref_code"], "item": item_name(rec["item"])})

    if lost:
        matches = find_matches(rec, store.open_found(rec["item"]))
        for m in matches:
            store.add_match(rec["id"], m["record"]["id"], m["score"])
        if matches:
            say(reply, f"Good news! {len(matches)} turned-in item(s) could be yours:")
            reply["messages"].append(match_cards(matches, today))
            say(reply, f"Go to the **{OFFICE}** with your **school ID** and your reference code. "
                       "They'll check it's yours before releasing it.")
        else:
            say(reply, "Nothing matching has been turned in yet. Your report stays on file, "
                       f"so ask me again later or check with the **{OFFICE}**.")
    else:
        say(reply, f"Please bring the item to the **{OFFICE}** and give them this code.")
        owners = find_owners(rec, store.open_lost(rec["item"]))
        for m in owners:
            store.add_match(m["record"]["id"], rec["id"], m["score"])
        if owners:
            say(reply, "Someone already reported losing something like this, "
                       "so the office will be able to reach them.")

    reply["state"] = new_state()
    reply["chips"] = [{"label": "Report another item", "action": "menu"},
                      {"label": "Search found items", "action": "SEARCH_ITEM"}]


def search(reply, store, today):
    st = reply["state"]
    slots = st["slots"]
    thing = item_name(slots["item"]).lower()
    results = find_matches(slots, store.open_found(slots["item"]), min_score=0)

    if results:
        say(reply, f"Here's what was turned in recently ({len(results)} {thing}):")
        reply["messages"].append(match_cards(results, today))
        say(reply, f"If one is yours, go to the **{OFFICE}** with your school ID and the reference code.")
        reply["chips"] = [{"label": "None of these are mine", "action": "keep:REPORT_LOST"},
                          {"label": "Main menu", "action": "menu"}]
    else:
        say(reply, f"No {thing} has been turned in yet. Want to file a lost report "
                   "so the office knows you're looking for it?")
        reply["chips"] = [{"label": "File a lost report", "action": "keep:REPORT_LOST"},
                          {"label": "Not now", "action": "menu"}]
    # keep the slots so "file a lost report" doesn't ask again
    reply["state"] = {**new_state(), "slots": slots}


def welcome(reply, text=None):
    reply["state"] = new_state()
    say(reply, text or "I'm **FindIt**, NU Laguna's lost and found assistant. Tell me what happened, "
                       "like *\"I lost my tumbler at the library yesterday\"*, or pick an option below.")
    reply["chips"] = MENU


def describe(slots, today):
    # readable version of what was picked up, for the chat and the nlp line
    out = {}
    if slots.get("item"):
        out["item"] = item_name(slots["item"])
    if slots.get("color"):
        out["color"] = slots["color"]
    if slots.get("brand"):
        out["brand"] = slots["brand"]
    if slots.get("location"):
        out["location"] = location_name(slots)
    if slots.get("date"):
        out["date"] = date_name(slots["date"], today)
    return out
