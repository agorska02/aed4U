// Import from many sources, duplicate detection and export — the same rules as backend/aed/importing.py
// (tests/import_cases.json runs against both). Used by the in-browser mock (api-mock.js).
// XLSX files are base64-encoded; they are unzipped with the browser's DecompressionStream, so XLSX
// parsing is asynchronous: use parseFileAsync() (parseFile() handles CSV, JSON and GeoJSON).
(function () {
  "use strict";

  var MAX_ROWS = 5000;
  var MAX_CONTENT_LENGTH = 2000000; // characters (XLSX: of the base64 text)
  var MAX_XLSX_PART_SIZE = 30000000; // bytes after unzipping one part (protects against zip bombs)
  var DUPLICATE_RADIUS_M = 15;
  var NAME_SIMILARITY_THRESHOLD = 0.5;
  var FORMATS = ["csv", "xlsx", "json", "geojson"];

  var MESSAGES = {
    format: "Nieobsługiwany format pliku. Dozwolone: CSV, XLSX, JSON, GeoJSON.",
    too_large: "Plik jest za duży (maks. 2 MB).",
    too_many_rows: "Plik ma za dużo rekordów (maks. {0}).",
    empty: "Plik nie zawiera żadnych rekordów.",
    csv_header: "Brak wiersza nagłówka z nazwami kolumn.",
    csv_duplicate_column: "Kolumna „{0}” występuje w nagłówku więcej niż raz.",
    csv_row_length: "Wiersz ma więcej wartości niż kolumn w nagłówku.",
    xls_old: "To plik w starym formacie Excela (.xls). Zapisz go jako .xlsx albo .csv (UTF-8).",
    xlsx_invalid: "Nie udało się odczytać pliku XLSX – sprawdź, czy to skoroszyt Excela (.xlsx).",
    xlsx_unnamed_column: "Kolumna {0} ma wartości, ale nie ma nazwy w pierwszym wierszu.",
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


  // --- XLSX (same steps as importing.py: unzip, then read the first sheet) ---------------------------------

  var XLSX_PARTS = ["xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/sharedStrings.xml", "xl/styles.xml"];
  var DATE_FORMAT_IDS = [14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47];
  var EXCEL_EPOCH = Date.UTC(1899, 11, 30); // serial 1 = 1900-01-01 (incl. Excel's 1900 leap-year bug)
  var EXCEL_EPOCH_1904 = Date.UTC(1904, 0, 1);

  function decodeBase64(content) {
    try {
      var binary = atob(content.trim());
      var bytes = new Uint8Array(binary.length);
      for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return bytes;
    } catch (e) {
      throw new ImportFileError(msg("xlsx_invalid"));
    }
  }

  // Central directory of a zip file: [{name, method, compressedSize, size, offset}]; throws on a broken file.
  function zipEntries(bytes) {
    var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    var end = -1;
    for (var i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
      if (view.getUint32(i, true) === 0x06054b50) { end = i; break; }
    }
    if (end === -1) throw new Error("no zip end record");
    var count = view.getUint16(end + 10, true);
    var offset = view.getUint32(end + 16, true);
    var entries = [];
    for (var n = 0; n < count; n++) {
      if (view.getUint32(offset, true) !== 0x02014b50) throw new Error("bad zip directory");
      var nameLength = view.getUint16(offset + 28, true);
      entries.push({
        name: new TextDecoder().decode(bytes.subarray(offset + 46, offset + 46 + nameLength)),
        method: view.getUint16(offset + 10, true),
        compressedSize: view.getUint32(offset + 20, true),
        size: view.getUint32(offset + 24, true),
        offset: view.getUint32(offset + 42, true)
      });
      offset += 46 + nameLength + view.getUint16(offset + 30, true) + view.getUint16(offset + 32, true);
    }
    return entries;
  }

  function unzipEntry(bytes, entry) {
    var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (view.getUint32(entry.offset, true) !== 0x04034b50) throw new Error("bad zip entry");
    var start = entry.offset + 30 + view.getUint16(entry.offset + 26, true) + view.getUint16(entry.offset + 28, true);
    var data = bytes.subarray(start, start + entry.compressedSize);
    var decode = function (buffer) {
      if (buffer.byteLength > MAX_XLSX_PART_SIZE) throw new ImportFileError(msg("too_large"));
      return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
    };
    if (entry.method === 0) return Promise.resolve(decode(data));
    if (entry.method !== 8 || typeof DecompressionStream === "undefined") throw new Error("unsupported compression");
    var stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
    return new Response(stream).arrayBuffer().then(function (buffer) { return decode(new Uint8Array(buffer)); });
  }

  // Unzip the parts of an XLSX workbook needed by readXlsx(): Promise of {part name: XML text}.
  function xlsxParts(bytes) {
    if (bytes[0] === 0xd0 && bytes[1] === 0xcf && bytes[2] === 0x11 && bytes[3] === 0xe0) {
      return Promise.reject(new ImportFileError(msg("xls_old"))); // OLE2 container: the old binary .xls
    }
    return Promise.resolve().then(function () {
      var wanted = zipEntries(bytes).filter(function (e) {
        return XLSX_PARTS.indexOf(e.name) !== -1 || /^xl\/worksheets\/[^/]+\.xml$/.test(e.name);
      });
      wanted.forEach(function (e) { if (e.size > MAX_XLSX_PART_SIZE) throw new ImportFileError(msg("too_large")); });
      return Promise.all(wanted.map(function (e) {
        return unzipEntry(bytes, e).then(function (text) { return [e.name, text]; });
      }));
    }).then(function (pairs) {
      var parts = {};
      pairs.forEach(function (p) { parts[p[0]] = p[1]; });
      return parts;
    }, function (e) {
      throw e instanceof ImportFileError ? e : new ImportFileError(msg("xlsx_invalid"));
    });
  }

  function children(node, name) {
    return Array.prototype.filter.call(node.children, function (c) { return c.localName === name; });
  }
  function descendants(node, name) { return Array.prototype.slice.call(node.getElementsByTagNameNS("*", name)); }
  function attr(node, name) { // by local name (r:id, xml:space... come with a namespace)
    for (var i = 0; i < node.attributes.length; i++) {
      if (node.attributes[i].localName === name) return node.attributes[i].value;
    }
    return null;
  }

  function xml(parts, name) {
    if (!(name in parts)) throw new ImportFileError(msg("xlsx_invalid"));
    var doc = new DOMParser().parseFromString(parts[name], "application/xml");
    if (doc.getElementsByTagName("parsererror").length) throw new ImportFileError(msg("xlsx_invalid"));
    return doc.documentElement;
  }

  // Text of a shared / inline string: plain <t> or rich-text runs <r><t>, without phonetic hints.
  function stringItem(node) {
    var texts = children(node, "t").map(function (t) { return t.textContent; });
    children(node, "r").forEach(function (run) {
      children(run, "t").forEach(function (t) { texts.push(t.textContent); });
    });
    return texts.join("");
  }

  // Indexes of cell styles (s="...") that show numbers as dates.
  function dateStyles(parts) {
    if (!("xl/styles.xml" in parts)) return [];
    var styles = xml(parts, "xl/styles.xml");
    var custom = {};
    descendants(styles, "numFmt").forEach(function (fmt) {
      var code = (attr(fmt, "formatCode") || "").replace(/"[^"]*"|\[[^\]]*\]|\\./g, "").toLowerCase();
      custom[Number(attr(fmt, "numFmtId"))] = /[dmyh]/.test(code) && code.indexOf("general") === -1;
    });
    var result = [];
    descendants(styles, "cellXfs").forEach(function (cellXfs) {
      children(cellXfs, "xf").forEach(function (xf, index) {
        var id = Number(attr(xf, "numFmtId") || 0);
        if (DATE_FORMAT_IDS.indexOf(id) !== -1 || custom[id]) result.push(index);
      });
    });
    return result;
  }

  function excelDate(serial, date1904) {
    var iso = new Date((date1904 ? EXCEL_EPOCH_1904 : EXCEL_EPOCH) + Math.round(serial * 86400) * 1000).toISOString();
    return iso.slice(11, 19) === "00:00:00" ? iso.slice(0, 10) : iso.slice(0, 19);
  }

  function excelNumber(text) {
    var value = Number(text);
    if (text.trim() === "" || isNaN(value)) throw new Error("not a number");
    return String(value); // shortest round-trip form, like repr() in Python (integers without ".0")
  }

  function columnIndex(ref) { // "C7" -> 2
    var letters = /^[A-Z]*/.exec(ref)[0];
    var index = 0;
    for (var i = 0; i < letters.length; i++) index = index * 26 + letters.charCodeAt(i) - 64;
    return index - 1;
  }

  function columnLetter(index) {
    var letters = "";
    index += 1;
    while (index) {
      var rest = (index - 1) % 26;
      letters = String.fromCharCode(65 + rest) + letters;
      index = Math.floor((index - 1) / 26);
    }
    return letters;
  }

  function firstSheetPath(parts) {
    var workbook = xml(parts, "xl/workbook.xml");
    var sheets = descendants(workbook, "sheet");
    if (!sheets.length) throw new ImportFileError(msg("xlsx_invalid"));
    var relId = attr(sheets[0], "id");
    var target = null;
    descendants(xml(parts, "xl/_rels/workbook.xml.rels"), "Relationship").forEach(function (rel) {
      if (target === null && attr(rel, "Id") === relId) target = attr(rel, "Target");
    });
    if (!target) throw new ImportFileError(msg("xlsx_invalid"));
    var date1904 = descendants(workbook, "workbookPr").some(function (pr) {
      return ["1", "true"].indexOf(attr(pr, "date1904")) !== -1;
    });
    return { path: target.charAt(0) === "/" ? target.replace(/^\/+/, "") : "xl/" + target, date1904: date1904 };
  }

  function cellValue(cell, shared, styles, date1904) {
    var kind = attr(cell, "t") || "n";
    if (kind === "inlineStr") {
      var inline = children(cell, "is");
      return inline.length ? stringItem(inline[0]) : "";
    }
    var values = children(cell, "v");
    var text = values.length ? values[0].textContent : "";
    if (text === "") return "";
    if (kind === "s") {
      var index = Number(text);
      if (!Number.isInteger(index) || index < 0 || index >= shared.length) throw new ImportFileError(msg("xlsx_invalid"));
      return shared[index];
    }
    if (kind === "b") return text === "1" ? "true" : "false";
    if (kind === "n") {
      try {
        if (styles.indexOf(Number(attr(cell, "s") || 0)) !== -1) return excelDate(Number(text), date1904);
        return excelNumber(text);
      } catch (e) {
        return text;
      }
    }
    return text; // "str" (formula result), "e" (error such as #N/A), "d" (ISO date)
  }

  // Rows of the first sheet as [[sheet row number, record]]; the first non-empty row holds column names.
  function readXlsx(parts) {
    var sheetInfo = firstSheetPath(parts);
    var shared = "xl/sharedStrings.xml" in parts
      ? children(xml(parts, "xl/sharedStrings.xml"), "si").map(stringItem) : [];
    var styles = dateStyles(parts);
    var sheet = xml(parts, sheetInfo.path);
    var table = [];
    descendants(sheet, "sheetData").forEach(function (data) {
      children(data, "row").forEach(function (row, position) {
        var number = Number(attr(row, "r") || position + 1);
        var values = {};
        children(row, "c").forEach(function (cell, column) {
          var ref = attr(cell, "r");
          values[ref ? columnIndex(ref) : column] = cellValue(cell, shared, styles, sheetInfo.date1904);
        });
        var filled = Object.keys(values).some(function (k) { return String(values[k]).trim() !== ""; });
        if (filled) table.push([number, values]);
      });
    });
    if (!table.length) throw new ImportFileError(msg("empty"));
    var header = {};
    var seen = {};
    Object.keys(table[0][1]).forEach(function (index) {
      var name = String(table[0][1][index]).trim();
      if (!name) return;
      if (seen[name]) throw new ImportFileError(msg("csv_duplicate_column", name));
      seen[name] = true;
      header[index] = name;
    });
    var order = Object.keys(header).map(Number).sort(function (a, b) { return a - b; });
    return table.slice(1).map(function (entry) {
      var values = entry[1];
      Object.keys(values).forEach(function (index) {
        if (!(index in header) && String(values[index]).trim() !== "") {
          throw new ImportFileError("Wiersz " + entry[0] + ": " + msg("xlsx_unnamed_column", columnLetter(Number(index))));
        }
      });
      var record = {};
      order.forEach(function (index) { record[header[index]] = index in values ? values[index] : ""; });
      return [entry[0], record];
    });
  }

  function checkContent(content, format) {
    if (FORMATS.indexOf(format) === -1 || typeof content !== "string") throw new ImportFileError(msg("format"));
    if (content.length > MAX_CONTENT_LENGTH) throw new ImportFileError(msg("too_large"));
  }

  // CSV, JSON, GeoJSON: returns [[rowNumber, record], ...]; throws ImportFileError.
  function parseFile(content, format) {
    checkContent(content, format);
    if (format === "xlsx") throw new Error("XLSX is read asynchronously: use parseFileAsync()");
    content = content.replace(/^﻿/, "");
    return checkRows(format === "csv" ? parseCsv(content) : parseJson(content));
  }

  // Any format (XLSX content in base64): Promise of rows; rejects with ImportFileError.
  function parseFileAsync(content, format) {
    return Promise.resolve().then(function () {
      checkContent(content, format);
      if (format !== "xlsx") return parseFile(content, format);
      return xlsxParts(decodeBase64(content)).then(function (parts) { return checkRows(readXlsx(parts)); });
    });
  }

  function checkRows(rows) {
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
    parseFileAsync: parseFileAsync,
    readXlsx: readXlsx,
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
