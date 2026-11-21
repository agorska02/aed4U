"""Import of AED records from many sources, duplicate detection and export of the unified dataset.

Pure Python (no Django imports) — used by the portal module (mcod.aed), the standalone demo server and
mirrored in frontend/aed-import.js for the in-browser mock (tests/import_cases.json runs against both).

Import flow: parse_file() -> plan_import() -> the caller applies the planned actions in one transaction.
A file with any invalid row is rejected as a whole, so a provider never ends up with half an import.
"""

import csv
import io
import json
import math
import re
import unicodedata

from .validation import field_names, fields, to_json_value, validate_record

MAX_ROWS = 5000
MAX_CONTENT_LENGTH = 2_000_000  # characters
DUPLICATE_RADIUS_M = 15
NAME_SIMILARITY_THRESHOLD = 0.5
FORMATS = ("csv", "json", "geojson")

MESSAGES = {
    "format": "Nieobsługiwany format pliku. Dozwolone: CSV, JSON, GeoJSON.",
    "too_large": "Plik jest za duży (maks. 2 MB).",
    "too_many_rows": "Plik ma za dużo rekordów (maks. {0}).",
    "empty": "Plik nie zawiera żadnych rekordów.",
    "csv_header": "Brak wiersza nagłówka z nazwami kolumn.",
    "csv_duplicate_column": "Kolumna „{0}” występuje w nagłówku więcej niż raz.",
    "csv_row_length": "Wiersz ma więcej wartości niż kolumn w nagłówku.",
    "unknown_columns": "Nieznane kolumny: {0}. Użyj nazw z szablonu (aed-template.csv).",
    "missing_columns": "Brak wymaganych kolumn: {0}.",
    "json_invalid": "Nieprawidłowy JSON: {0}.",
    "json_shape": 'Oczekiwano listy obiektów, obiektu {{"data": [...]}} albo GeoJSON FeatureCollection.',
    "json_record": "Rekord musi być obiektem JSON.",
    "geojson_point": "Geometria musi być punktem (Point) ze współrzędnymi [długość, szerokość].",
    "duplicate_source_id": "Identyfikator „{0}” występuje w pliku więcej niż raz (pierwszy raz: rekord {1}).",
}


def _message(key, *args):
    return MESSAGES[key].format(*args)


class ImportFileError(ValueError):
    """The file cannot be read at all (wrong format, header, size)."""


# --- parsing ------------------------------------------------------------------------------------------------


def parse_file(content, file_format):
    """Return a list of (row_number, record) where record maps column names to raw values.

    CSV row numbers are line numbers in the file (header = 1); JSON/GeoJSON numbers count records from 1.
    Raises ImportFileError for problems with the whole file.
    """
    if file_format not in FORMATS:
        raise ImportFileError(_message("format"))
    if not isinstance(content, str):
        raise ImportFileError(_message("format"))
    if len(content) > MAX_CONTENT_LENGTH:
        raise ImportFileError(_message("too_large"))
    content = content.lstrip("﻿")
    rows = _parse_csv(content) if file_format == "csv" else _parse_json(content)
    if not rows:
        raise ImportFileError(_message("empty"))
    if len(rows) > MAX_ROWS:
        raise ImportFileError(_message("too_many_rows", MAX_ROWS))
    _check_columns({name for _number, record in rows for name in record})
    return rows


def _parse_csv(content):
    first_line = content.split("\n", 1)[0]
    # Spreadsheets in Polish locale often save CSV with ";" — accept it, the rest of the rules stay the same.
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(content, newline=""), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        raise ImportFileError(_message("empty"))
    header = [name.strip() for name in header]
    if not any(header):
        raise ImportFileError(_message("csv_header"))
    seen = set()
    for name in header:
        if name in seen:
            raise ImportFileError(_message("csv_duplicate_column", name))
        seen.add(name)
    rows = []
    for values in reader:
        if not any(value.strip() for value in values):
            continue  # skip empty lines
        if len(values) > len(header):
            raise ImportFileError("Wiersz {0}: {1}".format(reader.line_num, _message("csv_row_length")))
        values = values + [""] * (len(header) - len(values))
        rows.append((reader.line_num, dict(zip(header, values))))
    return rows


def _parse_json(content):
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise ImportFileError(_message("json_invalid", exc))
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return [(number, _feature_record(feature)) for number, feature in enumerate(data.get("features") or [], 1)]
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        data = data["data"]
    if not isinstance(data, list):
        raise ImportFileError(_message("json_shape"))
    rows = []
    for number, record in enumerate(data, 1):
        if not isinstance(record, dict):
            raise ImportFileError("Rekord {0}: {1}".format(number, _message("json_record")))
        # JSON:API resource objects (our own export) carry the values in "attributes"
        if isinstance(record.get("attributes"), dict):
            record = dict(record["attributes"], id=record.get("id"))
        rows.append((number, record))
    return rows


def _feature_record(feature):
    geometry = (feature or {}).get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if geometry.get("type") != "Point" or not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ImportFileError(_message("geojson_point"))
    record = dict((feature or {}).get("properties") or {})
    record["longitude"], record["latitude"] = coordinates[0], coordinates[1]
    return record


def _check_columns(columns):
    known = set(field_names())
    unknown = sorted(columns - known)
    if unknown:
        raise ImportFileError(_message("unknown_columns", ", ".join(unknown)))
    required = [
        f["name"] for f in fields(provider_only=True) if f.get("constraints", {}).get("required") and f["name"] != "operator_name"
    ]
    missing = [name for name in required if name not in columns]
    if missing:
        raise ImportFileError(_message("missing_columns", ", ".join(missing)))


# --- duplicates ---------------------------------------------------------------------------------------------


def distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (haversine, mean Earth radius)."""
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


def _normalize_text(text):
    text = (text or "").lower().replace("ł", "l")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _bigrams(text):
    text = _normalize_text(text).replace(" ", "")
    return [text[i : i + 2] for i in range(len(text) - 1)]


def name_similarity(a, b):
    """Dice coefficient of character bigrams (0..1), diacritics and punctuation ignored."""
    first, second = _bigrams(a), _bigrams(b)
    if not first or not second:
        return 1.0 if _normalize_text(a) == _normalize_text(b) else 0.0
    remaining = list(second)
    common = 0
    for gram in first:
        if gram in remaining:
            remaining.remove(gram)
            common += 1
    return 2.0 * common / (len(first) + len(second))


def _same_address(a, b):
    keys = ("postal_code", "street_number")
    return all(_normalize_text(str(a.get(k) or "")) == _normalize_text(str(b.get(k) or "")) for k in keys) and bool(
        a.get("street_number")
    )


def find_duplicate(values, candidates, exclude_id=None):
    """Nearest candidate within DUPLICATE_RADIUS_M with a similar place name or the same address.

    `values` and each candidate are dicts with latitude, longitude, location_name, postal_code, street_number
    (candidates also "id"). Returns (candidate, distance in whole metres) or (None, None).
    """
    best, best_distance = None, None
    for candidate in candidates:
        if exclude_id is not None and candidate.get("id") == exclude_id:
            continue
        if candidate.get("latitude") is None or candidate.get("longitude") is None:
            continue
        distance = distance_m(values["latitude"], values["longitude"], candidate["latitude"], candidate["longitude"])
        if distance > DUPLICATE_RADIUS_M:
            continue
        similar = name_similarity(values.get("location_name"), candidate.get("location_name")) >= NAME_SIMILARITY_THRESHOLD
        if (similar or _same_address(values, candidate)) and (best_distance is None or distance < best_distance):
            best, best_distance = candidate, distance
    return (best, int(round(best_distance))) if best is not None else (None, None)


# --- planning -----------------------------------------------------------------------------------------------


def normalize(value):
    """Comparable representation of a stored or cleaned value ("" and None are both "no value")."""
    value = to_json_value(value)
    if value == "" or value is None:
        return None
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        return value.strip()
    return value


def plan_import(rows, own_records, all_records, default_operator):
    """Validate parsed rows and decide what to do with each of them.

    own_records: existing records of the importing institution (dicts with "id", "source_id" and schema
    fields) — a row with the same non-empty source_id updates that record.
    all_records: every existing record (any institution) — used to flag possible duplicates.

    Returns a dict:
      errors:  [{"row": n, "field": name, "message": text}, ...]  (empty = the file can be imported)
      actions: [{"row": n, "action": "create" | "update" | "unchanged", "values": cleaned, "record_id": id,
                 "duplicate_of": existing record id | None, "duplicate_of_row": row number in this file | None,
                 "duplicate_distance_m": m | None}, ...]
      summary: counts of rows, valid, invalid, create, update, unchanged, duplicates
    """
    by_source_id = {r["source_id"]: r for r in own_records if r.get("source_id")}
    provider_fields = field_names(provider_only=True)
    errors, actions = [], []
    first_row_of_source_id = {}
    invalid_rows = set()
    for number, record in rows:
        values, row_errors = validate_record(record, optional=("operator_name",))
        for field_name, message in row_errors.items():
            errors.append({"row": number, "field": field_name, "message": message})
            invalid_rows.add(number)
        source_id = values.get("source_id")
        if source_id:
            if source_id in first_row_of_source_id:
                message = _message("duplicate_source_id", source_id, first_row_of_source_id[source_id])
                errors.append({"row": number, "field": "source_id", "message": message})
                invalid_rows.add(number)
            else:
                first_row_of_source_id[source_id] = number
        if number in invalid_rows:
            continue
        values["operator_name"] = values["operator_name"] or default_operator
        existing = by_source_id.get(source_id) if source_id else None
        if existing is None:
            action = "create"
        elif any(normalize(values[name]) != normalize(existing.get(name)) for name in provider_fields):
            action = "update"
        else:
            action = "unchanged"
        # duplicates: other existing records and the rows planned so far in this file
        planned = [dict(a["values"], id="row:{0}".format(a["row"])) for a in actions if a["action"] != "unchanged"]
        duplicate, distance = (None, None)
        if action != "unchanged":
            duplicate, distance = find_duplicate(
                values, list(all_records) + planned, exclude_id=existing["id"] if existing else None
            )
        in_file = duplicate is not None and str(duplicate["id"]).startswith("row:")
        if duplicate is None:
            duplicate = {"id": None}
        actions.append(
            {
                "row": number,
                "action": action,
                "values": values,
                "record_id": existing["id"] if existing else None,
                "duplicate_of": None if in_file else duplicate["id"],
                "duplicate_of_row": int(duplicate["id"][4:]) if in_file else None,
                "duplicate_distance_m": distance,
            }
        )
    summary = {
        "rows": len(rows),
        "invalid": len(invalid_rows),
        "valid": len(rows) - len(invalid_rows),
        "create": sum(1 for a in actions if a["action"] == "create"),
        "update": sum(1 for a in actions if a["action"] == "update"),
        "unchanged": sum(1 for a in actions if a["action"] == "unchanged"),
        "duplicates": sum(1 for a in actions if a["duplicate_of"] is not None or a["duplicate_of_row"] is not None),
    }
    return {"errors": errors, "actions": actions, "summary": summary}


# --- export -------------------------------------------------------------------------------------------------


def export_record(record):
    """Stored record (schema fields + uuid, source, verified_at) -> row of the published dataset."""
    row = {}
    for field in fields():
        name = field["name"]
        value = to_json_value(record.get("uuid") if name == "id" else record.get(name))
        if name == "id" and value is not None:
            value = str(value)  # uuid.UUID from Django
        if field["type"] == "boolean" and value is not None and value != "":
            value = bool(value)  # SQLite stores booleans as 0/1
        if name in ("latitude", "longitude") and value is not None:
            value = round(float(value), 6)
        if isinstance(value, str) and name == "verified_at":
            value = value.replace("+00:00", "Z")
        row[name] = "" if value is None else value
    return row


def _csv_value(name, value):
    if value is True or value is False:
        return "true" if value else "false"
    if name in ("latitude", "longitude") and value != "":
        return "{0:.6f}".format(value)  # fixed 6 decimals (~0.1 m), as in the reference scope
    return value


def to_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=field_names(), lineterminator="\r\n")  # RFC 4180
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _csv_value(k, v) for k, v in row.items()})
    return out.getvalue()


def to_geojson(rows, data_date=None):
    features = []
    for row in rows:
        properties = {k: (None if v == "" else v) for k, v in row.items() if k not in ("latitude", "longitude")}
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
                "properties": properties,
            }
        )
    collection = {"type": "FeatureCollection", "features": features}
    if data_date:
        collection["metadata"] = {"data_date": data_date, "schema": "aed.schema.json"}
    return collection


def to_json(rows):
    return [{k: (None if v == "" else v) for k, v in row.items()} for row in rows]
