# tests full conversations the way a real user would have them, e.g. someone
# reports a found phone, then the owner reports it lost and gets a match.

from datetime import date

from findit.dialogue import respond
from findit.store import MemoryStore

TODAY = date(2026, 9, 26)


class Chat:
    # fakes a browser: keeps the state between messages like chat.js does
    def __init__(self, store=None):
        self.store = store or MemoryStore()
        self.state = None
        self.last = None

    def say(self, message=None, action=None):
        self.last = respond(self.state, message=message, action=action,
                            store=self.store, today=TODAY)
        self.state = self.last["state"]
        return self.last

    def texts(self):
        return " ".join(m.get("text", "") for m in self.last["messages"])

    def types(self):
        return [m["type"] for m in self.last["messages"]]


def test_full_lost_report_in_one_message():
    c = Chat()
    c.say("I lost my black iphone at the library yesterday")
    assert c.state["awaiting"] == "details"
    assert c.state["slots"]["item"] == "PHONE"
    assert c.state["slots"]["color"] == "black"

    c.say("it has a cracked screen")
    assert c.state["mode"] == "confirming"
    assert "report" in c.types()

    c.say("yes")
    assert "ticket" in c.types()
    assert c.store.lost[0]["description"] == "it has a cracked screen"
    assert c.state["mode"] == "idle"


def test_asks_for_missing_info_one_at_a_time():
    c = Chat()
    c.say("i lost something")
    assert c.state["awaiting"] == "item"
    c.say("my umbrela")
    assert c.state["slots"]["item"] == "UMBRELLA"
    assert c.state["awaiting"] == "location"
    c.say(action="set:location:GYM")
    assert c.state["awaiting"] == "date"
    c.say("kahapon")
    assert c.state["slots"]["date"] == "2026-09-25"
    assert c.state["awaiting"] == "details"


def test_found_then_lost_gets_matched():
    store = MemoryStore()
    finder = Chat(store)
    finder.say("I found a telecommunication device inside the gym today")
    finder.say("it's black")
    finder.say(action="confirm")
    assert store.found[0]["item"] == "PHONE"

    owner = Chat(store)
    owner.say("nawala ko yung cp ko sa gym kanina, black siya")
    owner.say(action="skip")
    owner.say(action="confirm")
    assert "matches" in owner.types()
    assert store.matches


def test_found_before_lost_date_is_not_a_match():
    store = MemoryStore()
    finder = Chat(store)
    finder.say("found a wallet at the cafeteria last monday")
    finder.say(action="skip")
    finder.say(action="confirm")

    owner = Chat(store)
    owner.say("i lost my wallet at the cafeteria today")
    owner.say(action="skip")
    owner.say(action="confirm")
    assert "matches" not in owner.types()


def test_cancel_mid_report():
    c = Chat()
    c.say("i lost my wallet")
    c.say("cancel")
    assert c.state["mode"] == "idle"
    assert "cancelled" in c.texts()


def test_change_details_on_confirm_card():
    c = Chat()
    c.say("i found keys at the lobby today")
    c.say(action="skip")
    assert c.state["mode"] == "confirming"
    c.say("actually it was at the library")
    assert c.state["mode"] == "confirming"
    assert c.state["slots"]["location"] == "LIBRARY"


def test_faq_question():
    c = Chat()
    c.say("where is the lost and found office?")
    assert "Disciplinary Office" in c.texts()
    assert c.last["nlp"]["intent"] == "GENERAL_INQUIRY"


def test_question_in_the_middle_of_a_report():
    c = Chat()
    c.say("i lost my tumbler")
    assert c.state["awaiting"] == "location"
    c.say("is there a fee to claim items?")
    assert "free" in c.texts()
    assert c.state["awaiting"] == "location"


def test_search_with_no_results_offers_report():
    c = Chat()
    c.say("has anyone turned in an umbrella?")
    assert "No umbrella" in c.texts()
    c.say(action="keep:REPORT_LOST")
    assert c.state["intent"] == "REPORT_LOST"
    assert c.state["slots"]["item"] == "UMBRELLA"


def test_unknown_place_is_kept_as_text():
    c = Chat()
    c.say("i found a watch")
    c.say("beside the big tree near building 2")
    assert c.state["slots"]["location"] == "OTHER"
    assert "big tree" in c.state["slots"]["location_detail"]


def test_bad_state_from_browser_is_ignored():
    c = Chat()
    c.state = {"mode": "confirming", "intent": "HACK", "slots": {"item": {"x": 1}}}
    c.say("hello")
    assert c.state["mode"] == "idle"
    assert "FindIt" in c.texts()
