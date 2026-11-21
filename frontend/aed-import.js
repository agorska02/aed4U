// Import from many sources, duplicate detection and export — the same rules as backend/aed/importing.py
// (tests/import_cases.json runs against both). Used by the in-browser mock (api-mock.js).
(function () {
  "use strict";

  var MAX_ROWS = 5000;
  var MAX_CONTENT_LENGTH = 2000000;
  var DUPLICATE_RADIUS_M = 15;
  var NAME_SIMILARITY_THRESHOLD = 0.5;
  var FORMATS = ["csv", "json", "geojson"];

  var MESSAGES = {
    format: "Nieobsługiwany format pliku. Dozwolone: CSV, JSON, GeoJSON.",
    too_large: "Plik jest za duży (maks. 2 MB).",
    too_many_rows: "Plik ma za dużo rekordów (maks. {0}).",
    empty: "Plik nie zawiera żadnych rekordów.",
    csv_header: "Brak wiersza nagłówka z nazwami kolumn.",
    csv_duplicate_column: "Kolumna „{0}” występuje w nagłówku więcej niż raz.",
    csv_row_length: "Wiersz ma więcej wartości niż kolumn w nagłówku.",
    unknown_columns: "Nieznane kolumny: {0}. Użyj nazw z szablonu (aed-template.csv).",
    missing_columns: "Brak wymaganych kolumn: {0}.",
    json_invalid: "Nieprawidłowy JSON: {0}.",
    json_shape: "Oczekiwano listy obiektów, obiektu {\"data\": [...]} albo GeoJSON FeatureCollection.",
    json_record: "Rekord musi być obiektem JSON.",
    geojson_point: "Geometria musi być punktem (Point) ze współrzędnymi [długość, szerokość].",
    same_device: "Ten sam producent i numer seryjny co w rekordzie {0} – jedno urządzenie może wystąpić tylko raz.",
    device_elsewhere: "To urządzenie (producent i numer seryjny) jest już zgłoszone przez inną instytucję – " +
      "skontaktuj się z administratorem portalu."
  };

  function msg(key) {
    var args = Array.prototype.slice.call(arguments, 1);
    return MESSAGES[key].replace(/\{(\d)\}/g, function (m, i) { return args[Number(i)]; });
  }

  function ImportFileError(message) { this.message = message; }

  function V() { return window.AedValidator; }
  function fieldNames(providerOnly) { return V().fields(providerOnly).map(function (f) { return f.name; }); }

  // --- parsing ---------------------------------------------------------------------------------------------

  // RFC 4180 reader; returns [{line: physical line number where the record ends, values: [...]}].
  function readCsv(text, delimiter) {
    var records = [];
    var values = [];
    var value = "";
    var quoted = false;
    var line = 0;
    var i = 0;
    var n = text.length;
    var started = false;
    function endRecord() {
      values.push(value);
      records.push({ line: line, values: values });
      values = [];
      value = "";
      started = false;
    }
    while (i < n) {
      var c = text[i];
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') { value += '"'; i += 2; continue; }
          quoted = false; i += 1; continue;
        }
        if (c === "\r" || c === "\n") {
          line += 1;
          if (c === "\r" && text[i + 1] === "\n") { value += "\r\n"; i += 2; continue; }
        }
        value += c; i += 1; continue;
      }
      if (c === '"' && value === "") { quoted = true; started = true; i += 1; continue; }
      if (c === delimiter) { values.push(value); value = ""; started = true; i += 1; continue; }
      if (c === "\r" || c === "\n") {
        line += 1;
        i += (c === "\r" && text[i + 1] === "\n") ? 2 : 1;
        endRecord();
        continue;
      }
      value += c; started = true; i += 1;
    }
    if (started || value !== "" || values.length) {
      line += 1;
      endRecord();
    }
    return records;
  }

  function parseCsv(content) {
    var firstLine = content.split("\n")[0];
    var delimiter = (firstLine.split(";").length > firstLine.split(",").length) ? ";" : ",";
    var records = readCsv(content, delimiter);
    if (!records.length) throw new ImportFileError(msg("empty"));
    var header = records[0].values.map(function (name) { return name.trim(); });
    if (!header.some(Boolean)) throw new ImportFileError(msg("csv_header"));
    var seen = {};
    header.forEach(function (name) {
      if (seen[name]) throw new ImportFileError(msg("csv_duplicate_column", name));
      seen[name] = true;
    });
    var rows = [];
    records.slice(1).forEach(function (record) {
      var values = record.values;
      if (!values.some(function (v) { return v.trim() !== ""; })) return;
      if (values.length > header.length) {
        throw new ImportFileError("Wiersz " + record.line + ": " + msg("csv_row_length"));
      }
      var row = {};
      header.forEach(function (name, index) { row[name] = index < values.length ? values[index] : ""; });
      rows.push([record.line, row]);
    });
    return rows;
  }

  function featureRecord(feature) {
    var geometry = (feature && feature.geometry) || {};
    var coordinates = geometry.coordinates;
    if (geometry.type !== "Point" || !Array.isArray(coordinates) || coordinates.length < 2) {
      throw new ImportFileError(msg("geojson_point"));
    }
    var record = {};
    var properties = (feature && feature.properties) || {};
    Object.keys(properties).forEach(function (k) { record[k] = properties[k]; });
    record.longitude = coordinates[0];
    record.latitude = coordinates[1];
    return record;
  }

  function parseJson(content) {
    var data;
    try { data = JSON.parse(content); } catch (e) { throw new ImportFileError(msg("json_invalid", e.message)); }
    if (data && !Array.isArray(data) && typeof data === "object" && data.type === "FeatureCollection") {
      return (data.features || []).map(function (feature, index) { return [index + 1, featureRecord(feature)]; });
    }
    if (data && !Array.isArray(data) && typeof data === "object" && Array.isArray(data.data)) data = data.data;
    if (!Array.isArray(data)) throw new ImportFileError(msg("json_shape"));
    return data.map(function (record, index) {
      if (!record || typeof record !== "object" || Array.isArray(record)) {
        throw new ImportFileError("Rekord " + (index + 1) + ": " + msg("json_record"));
      }
      if (record.attributes && typeof record.attributes === "object") {
        var flat = {};
        Object.keys(record.attributes).forEach(function (k) { flat[k] = record.attributes[k]; });
        flat.id = record.id;
        record = flat;
      }
      return [index + 1, record];
    });
  }

  function checkColumns(columns) {
    var known = fieldNames(false);
    var unknown = Object.keys(columns).filter(function (c) { return known.indexOf(c) === -1; }).sort();
    if (unknown.length) throw new ImportFileError(msg("unknown_columns", unknown.join(", ")));
    var missing = V().fields(true).filter(function (f) {
      return (f.constraints || {}).required && !columns[f.name];
    }).map(function (f) { return f.name; });
    if (missing.length) throw new ImportFileError(msg("missing_columns", missing.join(", ")));
  }

  // Returns [[rowNumber, record], ...]; throws ImportFileError.
  function parseFile(content, format) {
    if (FORMATS.indexOf(format) === -1 || typeof content !== "string") throw new ImportFileError(msg("format"));
    if (content.length > MAX_CONTENT_LENGTH) throw new ImportFileError(msg("too_large"));
    content = content.replace(/^﻿/, "");
    var rows = format === "csv" ? parseCsv(content) : parseJson(content);
    if (!rows.length) throw new ImportFileError(msg("empty"));
    if (rows.length > MAX_ROWS) throw new ImportFileError(msg("too_many_rows", MAX_ROWS));
    var columns = {};
    rows.forEach(function (row) { Object.keys(row[1]).forEach(function (k) { columns[k] = true; }); });
    checkColumns(columns);
    return rows;
  }

  // --- duplicates ------------------------------------------------------------------------------------------

  function distanceM(lat1, lon1, lat2, lon2) {
    var rad = Math.PI / 180;
    var p1 = lat1 * rad, p2 = lat2 * rad;
    var a = Math.pow(Math.sin((p2 - p1) / 2), 2) +
      Math.cos(p1) * Math.cos(p2) * Math.pow(Math.sin((lon2 - lon1) * rad / 2), 2);
    return 2 * 6371008.8 * Math.asin(Math.sqrt(a));
  }

  function normalizeText(text) {
    return String(text || "").toLowerCase().replace(/ł/g, "l")
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, " ").trim();
  }

  function bigrams(text) {
    var t = normalizeText(text).replace(/ /g, "");
    var out = [];
    for (var i = 0; i < t.length - 1; i++) out.push(t.slice(i, i + 2));
    return out;
  }

  function nameSimilarity(a, b) {
    var first = bigrams(a), second = bigrams(b);
    if (!first.length || !second.length) return normalizeText(a) === normalizeText(b) ? 1 : 0;
    var remaining = second.slice();
    var common = 0;
    first.forEach(function (gram) {
      var index = remaining.indexOf(gram);
      if (index !== -1) { remaining.splice(index, 1); common += 1; }
    });
    return 2 * common / (first.length + second.length);
  }

  function sameAddress(a, b) {
    return ["postal_code", "street_number"].every(function (k) {
      return normalizeText(a[k] === null || a[k] === undefined ? "" : a[k]) === normalizeText(b[k] === null || b[k] === undefined ? "" : b[k]);
    }) && !!a.street_number;
  }

  // Serial number for comparisons: upper case, letters and digits only ("ab-123 4" == "AB1234").
  function normalizeSerial(serial) { return String(serial || "").toUpperCase().replace(/[^A-Z0-9]/g, ""); }

  // Identity of a physical device: manufacturer + normalised serial number (see importing.device_key).
  function deviceKey(record) {
    var manufacturer = record.manufacturer;
    var serial = normalizeSerial(record.serial_number);
    if (!manufacturer || !serial) return null;
    if (manufacturer === "other") manufacturer = "other:" + normalizeText(record.manufacturer_other);
    return manufacturer + "|" + serial;
  }

  // Possible duplicate nearby — a warning for the administrator (see importing.find_duplicate).
  function findDuplicate(values, candidates, excludeId) {
    var best = null, bestDistance = null;
    candidates.forEach(function (candidate) {
      if (excludeId !== undefined && excludeId !== null && candidate.id === excludeId) return;
      if (candidate.latitude === null || candidate.latitude === undefined) return;
      if (candidate.longitude === null || candidate.longitude === undefined) return;
      var d = distanceM(values.latitude, values.longitude, candidate.latitude, candidate.longitude);
      if (d > DUPLICATE_RADIUS_M) return;
      var similar = nameSimilarity(values.location_name, candidate.location_name) >= NAME_SIMILARITY_THRESHOLD;
      if ((similar || sameAddress(values, candidate)) && (bestDistance === null || d < bestDistance)) {
        best = candidate;
        bestDistance = d;
      }
    });
    return best ? { candidate: best, distance: Math.round(bestDistance) } : { candidate: null, distance: null };
  }

  // --- planning --------------------------------------------------------------------------------------------

  function normalize(value) {
    if (value === "" || value === null || value === undefined) return null;
    if (typeof value === "number") return Math.round(value * 1e6) / 1e6;
    if (typeof value === "string") return value.trim();
    return value;
  }

  // Same contract as importing.plan_import().
  function planImport(rows, ownRecords, allRecords, institution) {
    var comparedFields = V().recordFieldNames();
    var errors = [], actions = [], rowOfKey = {}, invalid = {};
    var ownIds = ownRecords.map(function (r) { return r.id; });
    var byKey = {};
    allRecords.concat(ownRecords).forEach(function (r) { var k = deviceKey(r); if (k) byKey[k] = r; });
    rows.forEach(function (row) {
      var number = row[0];
      var result = V().validate(row[1]);
      var values = result.cleaned;
      Object.keys(result.errors).forEach(function (name) {
        errors.push({ row: number, field: name, message: result.errors[name] });
        invalid[number] = true;
      });
      if (invalid[number]) return;
      Object.keys(institution).forEach(function (k) { values[k] = institution[k]; });
      var key = deviceKey(values);
      if (rowOfKey[key] !== undefined) {
        errors.push({ row: number, field: "serial_number", message: msg("same_device", rowOfKey[key]) });
        invalid[number] = true;
        return;
      }
      rowOfKey[key] = number;
      var existing = byKey[key] || null;
      if (existing && ownIds.indexOf(existing.id) === -1) {
        errors.push({ row: number, field: "serial_number", message: msg("device_elsewhere") });
        invalid[number] = true;
        return;
      }
      var action = "create";
      if (existing) {
        action = comparedFields.some(function (name) { return normalize(values[name]) !== normalize(existing[name]); })
          ? "update" : "unchanged";
      }
      var duplicate = { candidate: null, distance: null };
      if (action !== "unchanged") {
        var planned = actions.filter(function (a) { return a.action !== "unchanged"; }).map(function (a) {
          var copy = {};
          Object.keys(a.values).forEach(function (k) { copy[k] = a.values[k]; });
          copy.id = "row:" + a.row;
          return copy;
        });
        duplicate = findDuplicate(values, allRecords.concat(planned), existing ? existing.id : null);
      }
      var inFile = !!duplicate.candidate && String(duplicate.candidate.id).indexOf("row:") === 0;
      actions.push({
        row: number,
        action: action,
        values: values,
        record_id: existing ? existing.id : null,
        duplicate_of: duplicate.candidate && !inFile ? duplicate.candidate.id : null,
        duplicate_of_row: inFile ? Number(String(duplicate.candidate.id).slice(4)) : null,
        duplicate_distance_m: duplicate.distance
      });
    });
    var count = function (kind) { return actions.filter(function (a) { return a.action === kind; }).length; };
    var invalidCount = Object.keys(invalid).length;
    return {
      errors: errors,
      actions: actions,
      summary: {
        rows: rows.length,
        invalid: invalidCount,
        valid: rows.length - invalidCount,
        create: count("create"),
        update: count("update"),
        unchanged: count("unchanged"),
        duplicates: actions.filter(function (a) { return a.duplicate_of !== null || a.duplicate_of_row !== null; }).length
      }
    };
  }

  // --- export ----------------------------------------------------------------------------------------------

  function exportRecord(record) {
    var row = {};
    V().publishedFieldNames().forEach(function (name) {
      var value = name === "id" ? record.uuid : record[name];
      if ((name === "latitude" || name === "longitude") && value !== null && value !== undefined) {
        value = Math.round(Number(value) * 1e6) / 1e6;
      }
      row[name] = value === null || value === undefined ? "" : value;
    });
    return row;
  }

  function csvCell(name, value) {
    var text = value === true ? "true" : value === false ? "false" : String(value);
    if ((name === "latitude" || name === "longitude") && value !== "") text = Number(value).toFixed(6);
    return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function toCsv(rows) {
    var names = V().publishedFieldNames();
    var lines = [names.join(",")];
    rows.forEach(function (row) { lines.push(names.map(function (n) { return csvCell(n, row[n]); }).join(",")); });
    return lines.join("\r\n") + "\r\n";
  }

  function nullify(row, skip) {
    var out = {};
    Object.keys(row).forEach(function (k) { if (!skip || skip.indexOf(k) === -1) out[k] = row[k] === "" ? null : row[k]; });
    return out;
  }

  function toGeojson(rows, dataDate) {
    var collection = {
      type: "FeatureCollection",
      features: rows.map(function (row) {
        return {
          type: "Feature",
          id: row.id,
          geometry: { type: "Point", coordinates: [row.longitude, row.latitude] },
          properties: nullify(row, ["latitude", "longitude"])
        };
      })
    };
    if (dataDate) collection.metadata = { data_date: dataDate, schema: "aed.schema.json" };
    return collection;
  }

  function toJson(rows) { return rows.map(function (row) { return nullify(row); }); }

  window.AedImport = {
    ImportFileError: ImportFileError,
    parseFile: parseFile,
    planImport: planImport,
    findDuplicate: findDuplicate,
    deviceKey: deviceKey,
    distanceM: distanceM,
    nameSimilarity: nameSimilarity,
    exportRecord: exportRecord,
    toCsv: toCsv,
    toGeojson: toGeojson,
    toJson: toJson,
    DUPLICATE_RADIUS_M: DUPLICATE_RADIUS_M
  };
})();
