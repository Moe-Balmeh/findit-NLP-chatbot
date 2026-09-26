# turns codes like WATER_BOTTLE into readable text like "Water bottle / tumbler"
# for the chat replies and report cards.

from datetime import date

NAMES = {
    "STUDENT_ID": "Student ID",
    "ID_LANYARD": "ID lanyard",
    "USB_DRIVE": "USB / flash drive",
    "BANK_CARD": "ATM / bank card",
    "WATER_BOTTLE": "Water bottle / tumbler",
    "OTHER": "Other",
    "LEARNING_RESOURCES_CENTER": "Learning Resources Center (LRC)",
    "AQUATICS_CENTER": "Aquatics Center / Pool",
    "SECURITY_GUARDHOUSE": "Guardhouse",
}


def item_name(code):
    if not code:
        return ""
    return NAMES.get(code, code.replace("_", " ").capitalize())


def location_name(slots):
    code = slots.get("location")
    if code == "OTHER":
        return slots.get("location_detail") or "Other"
    name = NAMES.get(code, (code or "").replace("_", " ").title())
    if slots.get("room"):
        name += f", Room {slots['room']}"
    if slots.get("floor"):
        name += f", floor {slots['floor']}"
    return name


def date_name(iso, today=None):
    if not iso:
        return "Not provided"
    if iso == "unknown":
        return "Not sure"
    d = date.fromisoformat(iso)
    label = f"{d:%B} {d.day}, {d.year}"
    if today and d == today:
        label += " (today)"
    return label
