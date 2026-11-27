"""
Room search that understands what people type.

The old search looked for the whole typed phrase inside one field, so
"single room mamelodi" found nothing (no field contains that phrase) and a
typo like "mid-rind" found nothing at all. This module:

- reads the query: room types ("bachelor", "ensuite", "res"...), a budget
  ("under 2500", "R2000", "2.5k", "1500-2500"), a postal code ("0122") and
  place / keyword words, ignoring filler ("room to rent near ...");
- matches every remaining word against the room's title, description and
  location fields (all words must match, in any field);
- corrects misspelt places and words against the places rooms are listed
  in plus a list of South African towns and suburbs: "mid-rind",
  "mud-rind" and "midrnd" all become "Midrand";
- if nothing matches every word, shows the rooms matching the most words
  instead of an empty page, and says so.

Pure Python + ordinary ORM filters, so it behaves the same on Postgres and
SQLite and needs no database extension.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from django.core.cache import cache
from django.db.models import Case, IntegerField, Q, Value, When

SEARCH_FIELDS = ("title", "description", "location", "suburb", "town", "city", "province", "room_type")

# Words people type that describe the room type (checked longest first).
ROOM_TYPE_PHRASES = {
    "student accommodation": "Student Accommodation",
    "student accomodation": "Student Accommodation",
    "student res": "Student Accommodation",
    "students": "Student Accommodation",
    "student": "Student Accommodation",
    "residence": "Student Accommodation",
    "res": "Student Accommodation",
    "single room": "Single Room",
    "single": "Single Room",
    "shared room": "Shared Room",
    "sharing": "Shared Room",
    "shared": "Shared Room",
    "bachelors": "Bachelor",
    "batchelor": "Bachelor",
    "bachelor": "Bachelor",
    "en suite": "Ensuite",
    "en-suite": "Ensuite",
    "ensuite": "Ensuite",
    "own bathroom": "Ensuite",
    "back room": "Backroom",
    "backroom": "Backroom",
    "backrooms": "Backroom",
    "outside room": "Backroom",
    "garden cottage": "Cottage",
    "granny flat": "Cottage",
    "cottage": "Cottage",
    "apartments": "Apartment",
    "apartment": "Apartment",
    "flats": "Apartment",
    "flat": "Apartment",
}

# Filler that says nothing about which room someone wants.
STOPWORDS = frozenset("""
a an the and or of in on at to for from by with near nearby around close closeby next
room rooms rent renting rental rentals let letting accommodation accomodation place places
looking look need needed want wanted find search i im me my we us please
available cheap affordable budget nice good clean safe area areas side
per month monthly pm p m pmonth rand rands r zar price
""".split())

# Short forms people use for big places.
ALIASES = {
    "jhb": "johannesburg", "joburg": "johannesburg", "jozi": "johannesburg", "jo burg": "johannesburg",
    "pta": "pretoria", "tshwane": "pretoria",
    "cpt": "cape town", "kaapstad": "cape town",
    "dbn": "durban",
    "pe": "gqeberha", "port elizabeth": "gqeberha",
}

# Towns and suburbs tenants search for, so a typo still finds the place
# even before many rooms are listed there. Rooms' own suburb/town/city
# values are added to this at runtime.
SA_PLACES: tuple[str, ...] = (
    # Tshwane / Pretoria
    "Pretoria", "Pretoria Central", "Pretoria West", "Pretoria North", "Arcadia", "Sunnyside", "Hatfield",
    "Brooklyn", "Menlo Park", "Lynnwood", "Garsfontein", "Faerie Glen", "Moreleta Park", "Waterkloof",
    "Centurion", "Midrand", "Mamelodi", "Mamelodi East", "Mamelodi West", "Soshanguve", "Mabopane",
    "Ga-Rankuwa", "Atteridgeville", "Laudium", "Saulsville", "Hammanskraal", "Temba", "Winterveld",
    "Akasia", "Rosslyn", "Wonderboom", "Montana", "Sinoville", "Eersterust", "Silverton", "Queenswood",
    "Capital Park", "Gezina", "Rietfontein", "Danville", "Kwaggasrand", "Lotus Gardens", "Olievenhoutbosch",
    "Erasmia", "Irene", "Highveld", "Rooihuiskraal", "Lyttelton", "Pierre van Ryneveld", "Equestria",
    "Silver Lakes", "Bronkhorstspruit", "Cullinan", "Rayton", "Refilwe", "Nellmapius", "Stinkwater",
    # Johannesburg
    "Johannesburg", "Johannesburg CBD", "Braamfontein", "Auckland Park", "Melville", "Brixton",
    "Hillbrow", "Berea", "Yeoville", "Doornfontein", "Rosebank", "Sandton", "Randburg", "Fourways",
    "Roodepoort", "Soweto", "Diepkloof", "Orlando", "Meadowlands", "Dobsonville", "Protea Glen",
    "Alexandra", "Diepsloot", "Cosmo City", "Lenasia", "Ennerdale", "Orange Farm", "Northcliff",
    "Linden", "Bryanston", "Rivonia", "Sunninghill", "Lonehill", "Kya Sand", "Mayfair", "Fordsburg",
    "Westdene", "Florida", "Honeydew", "Ferndale", "Greenside", "Parktown", "Killarney",
    # Ekurhuleni and West / East Rand
    "Tembisa", "Kempton Park", "Edenvale", "Germiston", "Boksburg", "Benoni", "Brakpan", "Springs",
    "Alberton", "Thokoza", "Katlehong", "Vosloorus", "Daveyton", "Tsakane", "KwaThema", "Duduza",
    "Olifantsfontein", "Ivory Park", "Rabie Ridge", "Krugersdorp", "Kagiso", "Randfontein",
    "Mohlakeng", "Westonaria", "Vereeniging", "Vanderbijlpark", "Sebokeng", "Evaton", "Sharpeville",
    # Other provinces' main towns
    "Cape Town", "Bellville", "Khayelitsha", "Mitchells Plain", "Stellenbosch", "Durbanville",
    "Durban", "Pinetown", "Umlazi", "KwaMashu", "Pietermaritzburg", "Gqeberha", "East London",
    "Bloemfontein", "Polokwane", "Mbombela", "Nelspruit", "Rustenburg", "Mahikeng", "Potchefstroom",
    "Kimberley", "Witbank", "Emalahleni", "Middelburg", "Secunda", "Klerksdorp", "Welkom",
    # Provinces
    "Gauteng", "Limpopo", "Mpumalanga", "North West", "Free State", "KwaZulu-Natal", "Western Cape",
    "Eastern Cape", "Northern Cape",
)

VOCAB_CACHE_KEY = "search_vocab_v2"
VOCAB_CACHE_SECONDS = 600
MIN_SCORE = 0.78
MAX_PRICE_SANE = 100_000


@dataclass
class ParsedQuery:
    raw: str
    terms: list[str] = field(default_factory=list)
    room_type: str = ""
    min_price: int | None = None
    max_price: int | None = None
    postal_code: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.terms or self.room_type or self.min_price or self.max_price or self.postal_code)


@dataclass
class SearchOutcome:
    """What the search did, for the "Showing results for..." line."""
    corrections: dict[str, str] = field(default_factory=dict)  # typed -> used
    mode: str = "all"  # "all" | "partial" | "none"
    relaxed_filters: bool = False  # dropped the type/budget read from the text
    rank_by_matches: bool = False


# ---------------------------------------------------------------- text --


def normalize(text: str) -> str:
    """Lowercase, no accents, letters/digits/spaces only. Hyphens and
    apostrophes join their word ("mid-rind" -> "midrind", "jo'burg" ->
    "joburg"); other punctuation becomes a space."""
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    # Thousands separators: "R2,500" and "R2 500" both mean 2500.
    text = re.sub(r"(\d)[,\s](\d{3})\b", r"\1\2", text)
    # Number ranges keep their meaning ("1500-2500" -> "1500 to 2500");
    # hyphens/apostrophes inside words just join them.
    text = re.sub(r"(\d)\s*-\s*(r?\s?\d)", r"\1 to \2", text)
    text = re.sub(r"(?<=[a-z])['’`-](?=[a-z])", "", text)
    text = re.sub(r"[^a-z0-9.\s]", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # keep decimal points ("2.5k")
    return " ".join(text.split())


def skeleton(word: str) -> str:
    """Consonant outline used to catch vowel typos: "midrand",
    "midrind" and "mudrind" all give "mdrnd"."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return ""
    word = word.replace("ph", "f").replace("ck", "k").replace("q", "k").replace("x", "ks")
    head, rest = word[0], re.sub(r"[aeiouyhw]", "", word[1:])
    out = head + rest
    return re.sub(r"(.)\1+", r"\1", out)


def similarity(a: str, b: str) -> float:
    """0..1, how likely `a` is a misspelling of `b` (both normalized,
    spaces removed)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    sa, sb = skeleton(a), skeleton(b)
    if len(sa) >= 3 and sa == sb:
        ratio = max(ratio, 0.92)
    elif len(sa) >= 3 and len(sb) >= 3:
        ratio = max(ratio, SequenceMatcher(None, sa, sb).ratio() * 0.9)
    # A different first letter is rarely a typo of a place name.
    if a[0] != b[0]:
        ratio *= 0.85
    return ratio


# ------------------------------------------------------------- parsing --


def _to_amount(number: str, k: str = "") -> int | None:
    try:
        value = float(number)
    except ValueError:
        return None
    if k:
        value *= 1000
    value = int(round(value))
    return value if 0 < value <= MAX_PRICE_SANE else None


AMOUNT = r"r?\s?(\d+(?:\.\d+)?)\s?(k)?"


def parse_query(raw: str) -> ParsedQuery:
    parsed = ParsedQuery(raw=raw)
    text = f" {normalize(raw)} "

    for short, full in ALIASES.items():
        text = re.sub(rf"\s{re.escape(short)}\s", f" {full} " if full else " ", text)

    # Budget: ranges first, then "under/over", then a bare amount.
    m = re.search(rf"\s(?:between\s)?{AMOUNT}\s?(?:to|and|-)\s?{AMOUNT}\s", text)
    if m:
        low, high = _to_amount(m.group(1), m.group(2) or ""), _to_amount(m.group(3), m.group(4) or "")
        if low and high and low <= high:
            parsed.min_price, parsed.max_price = low, high
            text = text.replace(m.group(0), " ", 1)
    m = re.search(rf"\s(?:under|below|less than|max|maximum|up to|upto|not more than|<)\s?{AMOUNT}\s", text)
    if m and parsed.max_price is None:
        parsed.max_price = _to_amount(m.group(1), m.group(2) or "")
        text = text.replace(m.group(0), " ", 1)
    m = re.search(rf"\s(?:over|above|from|min|minimum|more than|at least|>)\s?{AMOUNT}\s", text)
    if m and parsed.min_price is None:
        parsed.min_price = _to_amount(m.group(1), m.group(2) or "")
        text = text.replace(m.group(0), " ", 1)

    # Postal code: four digits starting with 0 (e.g. 0122, 0152).
    m = re.search(r"\s(0\d{3})\s", text)
    if m:
        parsed.postal_code = m.group(1)
        text = text.replace(m.group(0), " ", 1)

    # A bare amount ("R2000", "2.5k", "1800") reads as a budget ceiling.
    if parsed.max_price is None and parsed.min_price is None:
        m = re.search(r"\s(?:r\s?(\d+(?:\.\d+)?)\s?(k)?|(\d+(?:\.\d+)?)\s?(k)|(\d{3,6}))\s", text)
        if m:
            number = m.group(1) or m.group(3) or m.group(5)
            amount = _to_amount(number, m.group(2) or m.group(4) or "")
            if amount and amount >= 300:
                parsed.max_price = amount
                text = text.replace(m.group(0), " ", 1)

    for phrase in sorted(ROOM_TYPE_PHRASES, key=len, reverse=True):
        pattern = rf"\s{re.escape(normalize(phrase))}\s"
        if re.search(pattern, text):
            parsed.room_type = parsed.room_type or ROOM_TYPE_PHRASES[phrase]
            text = re.sub(pattern, " ", text, count=1)

    parsed.terms = [w for w in text.split() if w not in STOPWORDS and len(w) >= 2 and not w.isdigit()]
    return parsed


# ---------------------------------------------------------- vocabulary --


def place_vocabulary() -> dict[str, tuple[str, bool]]:
    """Normalized key (no spaces) -> (display name, is a full place name),
    for every listed place and every known South African place. Single
    words of multi-word names are included too (not full names), so
    "kempten" can still become "kempton"."""
    vocab = cache.get(VOCAB_CACHE_KEY)
    if vocab is not None:
        return vocab

    from .models import Room

    names: set[str] = set(SA_PLACES)
    rows = Room.objects.filter(is_available=True).values_list("suburb", "town", "city", "province", "location")
    for row in rows:
        for value in row:
            for part in re.split(r"[,/]", value or ""):
                part = part.strip()
                if 2 < len(part) <= 40:
                    names.add(part.title() if part.islower() else part)

    vocab = {}
    for name in sorted(names):
        norm = normalize(name)
        if not norm:
            continue
        vocab[norm.replace(" ", "")] = (name, True)
        for word in norm.split():
            if len(word) >= 4:
                vocab.setdefault(word, (word, False))
    cache.set(VOCAB_CACHE_KEY, vocab, VOCAB_CACHE_SECONDS)
    return vocab


def best_correction(term: str, vocab: dict[str, tuple[str, bool]] | None = None) -> tuple[str, float] | None:
    """The known place/word `term` most likely misspells, or None."""
    vocab = place_vocabulary() if vocab is None else vocab
    key = normalize(term).replace(" ", "")
    if len(key) < 3:
        return None
    best, best_score = None, 0.0
    for candidate, (display, _full) in vocab.items():
        if abs(len(candidate) - len(key)) > max(3, len(key) // 2):
            continue
        score = similarity(key, candidate)
        if score > best_score:
            best, best_score = display, score
    if best is not None and best_score >= MIN_SCORE and normalize(best).replace(" ", "") != key:
        return best, best_score
    return None


# -------------------------------------------------------------- search --


def _term_q(term: str) -> Q:
    q = Q()
    for name in SEARCH_FIELDS:
        q |= Q(**{f"{name}__icontains": term})
    return q


def apply_search(qs, parsed: ParsedQuery, *, use_type=True, use_price=True, allow_fuzzy=True):
    """Filters `qs` by the parsed query. Returns (queryset, SearchOutcome)."""
    outcome = SearchOutcome()

    def with_filters(base, type_ok, price_ok):
        if parsed.room_type and type_ok:
            base = base.filter(room_type=parsed.room_type)
        if parsed.min_price and price_ok:
            base = base.filter(price__gte=parsed.min_price)
        if parsed.max_price and price_ok:
            base = base.filter(price__lte=parsed.max_price)
        if parsed.postal_code:
            base = base.filter(postal_code__icontains=parsed.postal_code)
        return base

    filtered = with_filters(qs, use_type, use_price)

    # Settle each word: as typed if any room has it, else its correction.
    terms = []
    vocab = None
    for term in parsed.terms:
        if qs.filter(_term_q(term)).exists():
            terms.append(term)
            continue
        vocab = vocab if vocab is not None else place_vocabulary()
        # Same place, written differently ("ga-rankuwa" for "Ga-Rankuwa",
        # "mamelodieast" for "Mamelodi East"): use the proper spelling.
        known = vocab.get(normalize(term).replace(" ", ""))
        if known and known[1] and qs.filter(_term_q(known[0])).exists():
            terms.append(known[0])
            continue
        if allow_fuzzy:
            fix = best_correction(term, vocab)
            if fix and qs.filter(_term_q(fix[0])).exists():
                outcome.corrections[term] = fix[0]
                terms.append(fix[0])
                continue
            if fix:
                # A real place with no rooms yet: still say what we read.
                outcome.corrections[term] = fix[0]
                terms.append(fix[0])
                continue
        terms.append(term)

    strict = filtered
    for term in terms:
        strict = strict.filter(_term_q(term))
    if strict.exists():
        return strict, outcome

    # Budget/type read from the text left nothing: keep the place words.
    if (parsed.room_type and use_type) or ((parsed.min_price or parsed.max_price) and use_price):
        looser = with_filters(qs, False, False)
        for term in terms:
            looser = looser.filter(_term_q(term))
        if terms and looser.exists():
            outcome.relaxed_filters = True
            return looser, outcome

    # No room has every word: show those with the most of them.
    if len(terms) > 1:
        matches = sum(
            (Case(When(_term_q(t), then=Value(1)), default=Value(0), output_field=IntegerField()) for t in terms),
            Value(0),
        )
        partial = filtered.annotate(match_count=matches).filter(match_count__gte=1)
        if partial.exists():
            outcome.mode = "partial"
            outcome.rank_by_matches = True
            return partial, outcome

    outcome.mode = "none"
    return strict, outcome


def suggestions(prefix: str, limit: int = 6) -> list[dict]:
    """What to offer under the search box as someone types: room types and
    places, typo-tolerant ("mudr" still offers Midrand), places that have
    rooms first. Each item: {"label", "kind", "count"}."""
    from .models import Room

    key = normalize(prefix).replace(" ", "")
    if len(key) < 2:
        return []
    cache_key = f"search_suggest_v1:{key[:40]}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    available = Room.objects.filter(is_available=True)
    out = []

    if len(key) >= 3:
        types_seen = set()
        for phrase, room_type in ROOM_TYPE_PHRASES.items():
            if room_type not in types_seen and normalize(phrase).replace(" ", "").startswith(key):
                types_seen.add(room_type)
                out.append({"label": room_type, "kind": "type", "count": available.filter(room_type=room_type).count()})

    scored = []
    for candidate, (display, full) in place_vocabulary().items():
        if not full:
            continue
        if candidate.startswith(key):
            score = 1.0 + len(key) / max(len(candidate), 1)
        elif len(key) >= 3 and key in candidate:
            score = 0.95
        elif len(key) >= 3:
            score = similarity(key, candidate[: len(key) + 1])
            if score < MIN_SCORE:
                continue
        else:
            continue
        scored.append((score, display))
    scored.sort(key=lambda item: (-item[0], item[1]))

    places = []
    for _score, display in scored[: limit * 3]:
        places.append({"label": display, "kind": "place", "count": available.filter(_term_q(display)).count()})
    places.sort(key=lambda item: item["count"] == 0)  # stable: keeps best matches first in each group

    out = (out + places)[:limit]
    cache.set(cache_key, out, 60)
    return out
