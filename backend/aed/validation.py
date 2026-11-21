"""Validation of AED records against the reference data scope (hackathon/schema/aed.schema.json).

Pure Python (no Django imports), so the same rules are used by the portal module (mcod.aed), the standalone
demo server and file imports. frontend/aed-validator.js implements the same rules for the in-browser mock.

The schema is looked up in this order:
1. the AED_SCHEMA_PATH environment variable,
2. `<this package>/schema/aed.schema.json` (portal: mounted by docker-compose.hackathon.yml),
3. `hackathon/schema/aed.schema.json` (repository layout).
"""

import datetime
import json
import os
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_CANDIDATES = (HERE / "schema" / "aed.schema.json", HERE.parents[1] / "schema" / "aed.schema.json")

MAX_COORDINATE_DECIMALS = 6
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# Subset of the OpenStreetMap opening_hours syntax: "24/7" or rules like "Mo-Fr 08:00-16:00; Sa 09:00-13:00",
# "Mo-Su 00:00-24:00", "PH off". Enough for AED availability; the full grammar is not needed here.
_DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH)"
_DAYS = rf"{_DAY}(?:-{_DAY})?(?:,{_DAY}(?:-{_DAY})?)*"
_TIME = r"(?:[01][0-9]|2[0-4]):[0-5][0-9]"
_SPANS = rf"{_TIME}-{_TIME}(?:,{_TIME}-{_TIME})*"
_RULE = rf"(?:{_DAYS} )?(?:{_SPANS}|off|closed)"
OPENING_HOURS_RE = re.compile(rf"^(?:24/7|{_RULE}(?:; ?{_RULE})*)$")

MESSAGES = {
    "required": "Pole wymagane.",
    "type_string": "Podaj tekst.",
    "type_integer": "Podaj liczbę całkowitą.",
    "type_number": "Podaj liczbę z kropką jako separatorem dziesiętnym, np. 50.061389.",
    "type_boolean": "Dozwolone wartości: true, false.",
    "type_date": "Podaj datę w formacie RRRR-MM-DD.",
    "min_length": "Minimalna liczba znaków: {0}.",
    "max_length": "Maksymalna liczba znaków: {0}.",
    "minimum": "Wartość nie może być mniejsza niż {0}.",
    "maximum": "Wartość nie może być większa niż {0}.",
    "enum": "Dozwolone wartości: {0}.",
    "pattern": "Nieprawidłowy format.",
    "email": "Podaj poprawny adres e-mail.",
    "uuid": "Podaj identyfikator UUID.",
    "decimals": "Podaj najwyżej {0} miejsc po przecinku.",
    "opening_hours": "Użyj składni OpenStreetMap, np. 24/7 albo Mo-Fr 08:00-16:00; Sa 09:00-13:00.",
    "unknown": "Nieznane pole – sprawdź nazwę kolumny w schemacie.",
    "only_if": "Wypełnij tylko, gdy wybrano „{0}”.",
}

# Field-specific messages for pattern constraints (more helpful than "invalid format").
PATTERN_MESSAGES = {
    "operator_regon": "REGON to 9 lub 14 cyfr, bez spacji.",
    "postal_code": "Kod pocztowy w formacie NN-NNN, np. 31-004.",
    "contact_phone": "Numer telefonu to 9 cyfr, bez spacji i prefiksu +48.",
    "internal_contact_phone": "Numer telefonu to 9 cyfr, bez spacji i prefiksu +48.",
}


def schema_path():
    env = os.environ.get("AED_SCHEMA_PATH")
    if env:
        return Path(env)
    for candidate in SCHEMA_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("aed.schema.json not found; set AED_SCHEMA_PATH")


@lru_cache(maxsize=None)
def load_schema(path=None):
    with open(str(path or schema_path()), encoding="utf-8") as fh:
        return json.load(fh)


def is_provider_field(field):
    """Entered by the data provider: not set by the system (x-system) nor taken from the institution profile."""
    return not field.get("x-system") and not field.get("x-from-institution")


def fields(schema=None, provider_only=False):
    schema = schema or load_schema()
    return [f for f in schema["fields"] if not provider_only or is_provider_field(f)]


def field_names(schema=None, provider_only=False):
    return [f["name"] for f in fields(schema, provider_only)]


def record_field_names(schema=None):
    """Fields stored with a report: everything except system fields (provider + institution + internal)."""
    return [f["name"] for f in fields(schema) if not f.get("x-system")]


def institution_field_names(schema=None):
    return [f["name"] for f in fields(schema) if f.get("x-from-institution")]


def published_field_names(schema=None):
    """Columns of the published dataset (x-internal fields are for the portal administrator only)."""
    return [f["name"] for f in fields(schema) if not f.get("x-internal")]


def enum_choices(name, schema=None):
    """[(code, label), ...] for an enum field, labels from x-enumLabels (code if missing)."""
    field = next(f for f in fields(schema) if f["name"] == name)
    labels = field.get("x-enumLabels", {})
    return [(code, labels.get(code, code)) for code in field["constraints"]["enum"]]


class FieldError(ValueError):
    def __init__(self, key, *args):
        message = PATTERN_MESSAGES.get(args[0]) if key == "pattern" and args else None
        super().__init__(message or MESSAGES[key].format(*args))


def _is_missing(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_string(value):
    if not isinstance(value, str):
        raise FieldError("type_string")
    return value.strip()


def _to_integer(value):
    if isinstance(value, bool):
        raise FieldError("type_integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
        return int(value.strip())
    raise FieldError("type_integer")


def _to_number(value):
    if isinstance(value, bool):
        raise FieldError("type_number")
    text = repr(value) if isinstance(value, float) else str(value).strip()
    if not isinstance(value, (int, float, str)) or not re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", text):
        raise FieldError("type_number")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise FieldError("type_number")
    if -number.as_tuple().exponent > MAX_COORDINATE_DECIMALS:
        raise FieldError("decimals", MAX_COORDINATE_DECIMALS)
    return number


def _to_boolean(value, field):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text in field.get("trueValues", ["true"]):
            return True
        if text in field.get("falseValues", ["false"]):
            return False
    raise FieldError("type_boolean")


def _to_date(value):
    if isinstance(value, datetime.datetime):
        raise FieldError("type_date")
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value.strip()):
        try:
            return datetime.date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise FieldError("type_date")


def clean_value(field, value):
    """Convert one raw value (CSV text or JSON value) to a Python value and check the field constraints.

    Raises FieldError. Missing values ("" or None) must be handled by the caller.
    """
    kind = field["type"]
    if kind == "integer":
        value = _to_integer(value)
    elif kind == "number":
        value = _to_number(value)
    elif kind == "boolean":
        value = _to_boolean(value, field)
    elif kind == "date":
        value = _to_date(value)
    else:
        value = _to_string(value)

    constraints = field.get("constraints", {})
    if isinstance(value, str):
        if "minLength" in constraints and len(value) < constraints["minLength"]:
            raise FieldError("min_length", constraints["minLength"])
        if "maxLength" in constraints and len(value) > constraints["maxLength"]:
            raise FieldError("max_length", constraints["maxLength"])
        if "pattern" in constraints and not re.fullmatch(constraints["pattern"], value):
            raise FieldError("pattern", field["name"])
        if field.get("format") == "email" and not EMAIL_RE.match(value):
            raise FieldError("email")
        if field.get("format") == "uuid" and not UUID_RE.match(value):
            raise FieldError("uuid")
        if field["name"] == "opening_hours" and not OPENING_HOURS_RE.match(value):
            raise FieldError("opening_hours")
    if "enum" in constraints and value not in constraints["enum"]:
        raise FieldError("enum", ", ".join(constraints["enum"]))
    if "minimum" in constraints and value < Decimal(str(constraints["minimum"])):
        raise FieldError("minimum", constraints["minimum"])
    if "maximum" in constraints and value > Decimal(str(constraints["maximum"])):
        raise FieldError("maximum", constraints["maximum"])
    return value


def validate_record(record, schema=None, provider=True, optional=()):
    """Validate one AED record (dict of raw values).

    provider=True: the record comes from a data provider (form or import) — fields marked x-system or
    x-from-institution are ignored (the server sets them), so a previously exported file can be imported again.
    provider=False: a row of the published dataset — every field except x-internal ones is checked.
    optional: names of required fields that the caller fills in itself.

    Returns (cleaned, errors): `cleaned` has every checked field (None if missing); `errors` maps a field
    name to a message (empty if the record is valid).
    """
    schema_fields = [f for f in fields(schema, provider_only=provider) if provider or not f.get("x-internal")]
    known = {f["name"] for f in fields(schema)}
    cleaned, errors = {}, {}
    for name in record:
        if name not in known:
            errors[name] = MESSAGES["unknown"]
    for field in schema_fields:
        name = field["name"]
        raw = record.get(name)
        if _is_missing(raw):
            cleaned[name] = None
            if field.get("constraints", {}).get("required") and name not in optional:
                errors[name] = MESSAGES["required"]
            continue
        try:
            cleaned[name] = clean_value(field, raw)
        except FieldError as exc:
            errors[name] = str(exc)
    _check_required_if(schema_fields, cleaned, errors, optional)
    return cleaned, errors


def _check_required_if(schema_fields, cleaned, errors, optional):
    """x-requiredIf {other: value}: required when `other` has that value, and allowed only then."""
    by_name = {f["name"]: f for f in schema_fields}
    for field in schema_fields:
        condition = field.get("x-requiredIf")
        if not condition or field["name"] in errors:
            continue
        other, expected = next(iter(condition.items()))
        if other not in by_name:
            continue
        applies = cleaned.get(other) == expected
        if applies and cleaned.get(field["name"]) is None and field["name"] not in optional:
            errors[field["name"]] = MESSAGES["required"]
        elif not applies and cleaned.get(field["name"]) is not None:
            label = by_name[other].get("x-enumLabels", {}).get(expected, expected)
            errors[field["name"]] = MESSAGES["only_if"].format(label)


def to_json_value(value):
    """JSON/CSV-friendly representation of a cleaned value."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value
