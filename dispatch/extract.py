"""Pull structured fields out of free-form breakdown messages.

Drivers describe a fault in whatever words they use, mixing Indonesian and
English. Reporting needs columns. This module turns one into the other.

One rule runs through all of it. A field the message does not state comes back as
None. An empty cell in a report is a question someone can answer, while a guessed
plate number sends a truck to the wrong place, so nothing here infers a value it
did not read.
"""
import re

# Wheel position, checked before fault type so "ban depan" resolves both.
_POSITIONS = (
    ('front', (r'\bdepan\b', r'\bfront\b')),
    ('rear', (r'\bbelakang\b', r'\brear\b', r'\bback\b')),
)

# Fault categories. Ordered, first match wins.
_FAULTS = (
    ('tyre', (r'\bban\b', r'\btyre\b', r'\btire\b', r'\bpecah ban\b',
              r'\bbocor\b', r'\bblown\b', r'\bflat\b', r'\bkempes\b')),
    ('battery', (r'\baki\b', r'\bbattery\b', r'\bsoak\b', r'\bstarter\b',
                 r'\bmogok listrik\b')),
    ('engine', (r'\bmesin\b', r'\bengine\b', r'\boverheat\b', r'\bpanas\b',
                r'\bmogok\b')),
    ('fuel', (r'\bbensin\b', r'\bsolar\b', r'\bfuel\b', r'\bdiesel\b',
              r'\bkehabisan bahan bakar\b')),
    ('brake', (r'\brem\b', r'\bbrake\b', r'\bblong\b')),
)

# Indonesian plates: 1-2 letters, 1-4 digits, 1-3 letters, spacing optional.
# Generic fleet codes such as CA123456 are also accepted.
_PLATE_PATTERNS = (
    r'\b([A-Z]{1,2}\s?\d{1,4}\s?[A-Z]{1,3})\b',
    r'\b([A-Z]{2}\d{4,6})\b',
)

# Road names, longest form first so "tol dalam kota" beats "tol".
_ROAD_PATTERNS = (
    r'\b(tol\s+[a-z]+(?:\s+[a-z]+)?)\b',
    r'\b(jalan\s+[a-z]+(?:\s+[a-z]+)?)\b',
    r'\b(jl\.?\s+[a-z]+(?:\s+[a-z]+)?)\b',
    r'\b([nm]\d\s+(?:north|south|east|west))\b',
    r'\b([nm]\d)\b',
)

_ID_MARKERS = (r'\bpecah\b', r'\bban\b', r'\btol\b', r'\bbelakang\b', r'\bdepan\b',
               r'\bbocor\b', r'\bmogok\b', r'\baki\b', r'\bjalan\b', r'\brusak\b',
               r'\bbantuan\b', r'\btolong\b', r'\bkendaraan\b')
_EN_MARKERS = (r'\bblown\b', r'\btyre\b', r'\btire\b', r'\bfront\b', r'\brear\b',
               r'\bnorth\b', r'\bsouth\b', r'\bbroken\b', r'\bhelp\b',
               r'\bbreakdown\b', r'\btruck\b', r'\bflat\b')

# Words that look like plates but are not: road codes and unit labels.
_PLATE_BLOCKLIST = re.compile(r'^(?:[NM]\d|KM|TOL|JL)$', re.I)


def _first_match(text, patterns):
    for pattern in patterns:
        found = re.search(pattern, text, re.I)
        if found:
            return found
    return None


def _find_plate(original):
    """Read a plate from the original casing, since plates are upper case."""
    for pattern in _PLATE_PATTERNS:
        for candidate in re.findall(pattern, original):
            cleaned = re.sub(r'\s+', '', candidate).upper()
            if _PLATE_BLOCKLIST.match(cleaned):
                continue
            # A plate carries at least one digit and one letter.
            if re.search(r'\d', cleaned) and re.search(r'[A-Z]', cleaned):
                return cleaned
    return None


def _find_km(text):
    found = re.search(r'\bkm\.?\s*(\d+(?:[.,]\d+)?)', text, re.I)
    if not found:
        found = re.search(r'\b(\d+(?:[.,]\d+)?)\s*km\b', text, re.I)
    if not found:
        return None
    try:
        return float(found.group(1).replace(',', '.'))
    except ValueError:
        return None


def _find_road(text):
    found = _first_match(text, _ROAD_PATTERNS)
    if not found:
        return None
    road = re.sub(r'\s+', ' ', found.group(1)).strip()
    # Drop a trailing "km" that the pattern may have swallowed.
    road = re.sub(r'\s+km$', '', road, flags=re.I)
    return road.title()


def _find_language(text):
    id_hits = sum(bool(re.search(p, text, re.I)) for p in _ID_MARKERS)
    en_hits = sum(bool(re.search(p, text, re.I)) for p in _EN_MARKERS)
    if id_hits == 0 and en_hits == 0:
        return None
    return 'id' if id_hits >= en_hits else 'en'


def extract_fault_report(message):
    """Return structured fields read from a breakdown message.

    Keys are always present. Any field the message does not state is None, so a
    report can show a blank cell rather than an invented value.
    """
    original = message or ''
    text = original.lower()

    fault = None
    for name, patterns in _FAULTS:
        if _first_match(text, patterns):
            fault = name
            break

    position = None
    for name, patterns in _POSITIONS:
        if _first_match(text, patterns):
            position = name
            break

    report = {
        'plate': _find_plate(original),
        'fault_type': fault,
        'position': position,
        'road': _find_road(text),
        'km': _find_km(text),
        'language': _find_language(text),
        'raw_text': original,
    }

    counted = ('plate', 'fault_type', 'position', 'road', 'km')
    report['completeness'] = sum(report[k] is not None for k in counted)
    return report
