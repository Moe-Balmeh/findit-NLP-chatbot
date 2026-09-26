# text helpers used by every other file: lowercase, split into words, and
# measure how far apart two words are (for typos like "walet").
# keeping this in one place means every message gets cleaned the same way.

import re
import unicodedata

CONTRACTIONS = {
    "i'd": "i would",
    "i'm": "i am",
    "can't": "cannot",
    "cant": "cannot",
    "don't": "do not",
    "didn't": "did not",
    "doesn't": "does not",
    "won't": "will not",
    "isn't": "is not",
    "wasn't": "was not",
    "there's": "there is",
    "what's": "what is",
    "it's": "it is",
}

# real words that should never get "typo corrected" into an item or place
COMMON_WORDS = set("""
a an the and or but if so to of in on at by for from with without into onto near
around inside outside beside behind between under over after before during since
until while about above below this that these those there here where when what which
who whom whose why how i me my mine we us our you your he him his she her it its they
them their is am are was were be been being do does did done have has had having can
could will would shall should may might must not no yes ok okay pls please thanks
thank hello hi hey po lang naman ba na pa ko ako mo niya yung ang ng sa mga may
meron wala dito doon kasi pero tapos din rin kanina kahapon ngayon bukas lost lose
losing found find finding finds left leave forgot forget misplaced missing dropped
drop saw see seen someone somebody anyone anybody everyone item items thing things
stuff something anything nothing report reported reporting surrender surrendered
turn turned return returned claim claimed check checked search searched look looking
looked help today yesterday tomorrow morning afternoon evening night noon time day
days week last next ago earlier later just still already also too very really maybe
think thought know want wanted need needed like got get give gave take took taken
put keep kept brought bring bringing carry carried came come go went gone walk walked
class classes subject exam quiz school campus building floor level black white red
blue green yellow gray grey brown pink purple orange gold silver navy maroon beige
new old big small color colour one two three four five first second third fourth
fifth charged charging changed watched watching matched catch match rang bring
bags ring rings sure again back other another some any all each every many much
more most less same different right left side area place way part hours hour
office open close closed free fee pay paid process steps procedure name
list lists table tables count could bus friend friends
nakita nakitang makita nakakita naiwan nawala nawawala napulot nakapulot nahulog
nahanap mahanap hanapin gamit kunin pwede saan paano anong oras ano yung tong ito
iyan akong sila siya kami tayo lahat pacheck naisurrender nagsurrender isurrender
""".split())

_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize(text):
    text = unicodedata.normalize("NFKC", str(text)).lower()
    text = text.replace("’", "'").replace("‘", "'")
    return _WS.sub(" ", text).strip()


def expand_contractions(text):
    for short, full in CONTRACTIONS.items():
        text = re.sub(rf"(?<![a-z']){re.escape(short)}(?![a-z'])", full, text)
    return text


def tokenize(text):
    # "men's room" -> mens room, "drop-off" -> drop off
    text = expand_contractions(normalize(text))
    text = text.replace("'", "")
    return _TOKEN.findall(text)


def edit_distance(a, b):
    # optimal string alignment, so swapped letters ("noteobok") count as 1
    prev2 = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if (i > 1 and j > 1 and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]
