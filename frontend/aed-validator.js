// Validation of AED records against the reference data scope (window.AED_SCHEMA, see aed-schema.js).
// Same rules and messages as backend/aed/validation.py — keep both in sync
// (tests/validation_cases.json is run against both implementations).
(function () {
  "use strict";

  var MAX_COORDINATE_DECIMALS = 6;
  var EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  var UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

  // Subset of the OpenStreetMap opening_hours syntax (see validation.py).
  var DAY = "(?:Mo|Tu|We|Th|Fr|Sa|Su|PH)";
  var DAYS = DAY + "(?:-" + DAY + ")?(?:," + DAY + "(?:-" + DAY + ")?)*";
  var TIME = "(?:[01][0-9]|2[0-4]):[0-5][0-9]";
  var SPANS = TIME + "-" + TIME + "(?:," + TIME + "-" + TIME + ")*";
  var RULE = "(?:" + DAYS + " )?(?:" + SPANS + "|off|closed)";
  var OPENING_HOURS_RE = new RegExp("^(?:24/7|" + RULE + "(?:; ?" + RULE + ")*)$");

  var MESSAGES = {
    required: "Pole wymagane.",
    type_string: "Podaj tekst.",
    type_integer: "Podaj liczbę całkowitą.",
    type_number: "Podaj liczbę z kropką jako separatorem dziesiętnym, np. 50.061389.",
    type_boolean: "Dozwolone wartości: true, false.",
    type_date: "Podaj datę w formacie RRRR-MM-DD.",
    min_length: "Minimalna liczba znaków: {0}.",
    max_length: "Maksymalna liczba znaków: {0}.",
    minimum: "Wartość nie może być mniejsza niż {0}.",
    maximum: "Wartość nie może być większa niż {0}.",
    "enum": "Dozwolone wartości: {0}.",
    pattern: "Nieprawidłowy format.",
    email: "Podaj poprawny adres e-mail.",
    uuid: "Podaj identyfikator UUID.",
    decimals: "Podaj najwyżej {0} miejsc po przecinku.",
    opening_hours: "Użyj składni OpenStreetMap, np. 24/7 albo Mo-Fr 08:00-16:00; Sa 09:00-13:00.",
    unknown: "Nieznane pole – sprawdź nazwę kolumny w schemacie."
  };

  var PATTERN_MESSAGES = {
    operator_regon: "REGON to 9 lub 14 cyfr, bez spacji.",
    teryt_terc: "Kod TERC to 7 cyfr, np. 1261011.",
    teryt_simc: "Kod SIMC to 7 cyfr, np. 0950463.",
    postal_code: "Kod pocztowy w formacie NN-NNN, np. 31-004.",
    contact_phone: "Numer telefonu to 9 cyfr, bez spacji i prefiksu +48."
  };

  function FieldError(key, arg) {
    var message = key === "pattern" && PATTERN_MESSAGES[arg] ? PATTERN_MESSAGES[arg] : MESSAGES[key];
    this.message = message.replace("{0}", arg);
  }

  function schema() { return window.AED_SCHEMA; }

  function fields(providerOnly) {
    return schema().fields.filter(function (f) { return !(providerOnly && f["x-system"]); });
  }

  function isMissing(value) {
    return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
  }

  function toString(value) {
    if (typeof value !== "string") throw new FieldError("type_string");
    return value.trim();
  }

  function toInteger(value) {
    if (typeof value === "number" && Number.isInteger(value)) return value;
    if (typeof value === "string" && /^-?[0-9]+$/.test(value.trim())) return parseInt(value.trim(), 10);
    throw new FieldError("type_integer");
  }

  function toNumber(value) {
    var text;
    if (typeof value === "number" && isFinite(value)) text = String(value);
    else if (typeof value === "string") text = value.trim();
    else throw new FieldError("type_number");
    var match = /^-?[0-9]+(?:\.([0-9]+))?$/.exec(text);
    if (!match) throw new FieldError("type_number");
    if (match[1] && match[1].length > MAX_COORDINATE_DECIMALS) throw new FieldError("decimals", MAX_COORDINATE_DECIMALS);
    return parseFloat(text);
  }

  function toBoolean(value, field) {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") {
      var text = value.trim();
      if ((field.trueValues || ["true"]).indexOf(text) !== -1) return true;
      if ((field.falseValues || ["false"]).indexOf(text) !== -1) return false;
    }
    throw new FieldError("type_boolean");
  }

  function toDate(value) {
    if (typeof value === "string" && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value.trim())) {
      var text = value.trim();
      var parts = text.split("-").map(Number);
      var date = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
      if (date.getUTCFullYear() === parts[0] && date.getUTCMonth() === parts[1] - 1 && date.getUTCDate() === parts[2]) {
        return text;
      }
    }
    throw new FieldError("type_date");
  }

  // Returns the cleaned value (dates as "YYYY-MM-DD" strings) or throws FieldError.
  function cleanValue(field, value) {
    var kind = field.type;
    if (kind === "integer") value = toInteger(value);
    else if (kind === "number") value = toNumber(value);
    else if (kind === "boolean") value = toBoolean(value, field);
    else if (kind === "date") value = toDate(value);
    else value = toString(value);

    var c = field.constraints || {};
    if (typeof value === "string" && kind !== "date") {
      if (c.minLength !== undefined && value.length < c.minLength) throw new FieldError("min_length", c.minLength);
      if (c.maxLength !== undefined && value.length > c.maxLength) throw new FieldError("max_length", c.maxLength);
      if (c.pattern && !new RegExp(c.pattern).test(value)) throw new FieldError("pattern", field.name);
      if (field.format === "email" && !EMAIL_RE.test(value)) throw new FieldError("email");
      if (field.format === "uuid" && !UUID_RE.test(value)) throw new FieldError("uuid");
      if (field.name === "opening_hours" && !OPENING_HOURS_RE.test(value)) throw new FieldError("opening_hours");
    }
    if (c["enum"] && c["enum"].indexOf(value) === -1) throw new FieldError("enum", c["enum"].join(", "));
    if (c.minimum !== undefined && value < c.minimum) throw new FieldError("minimum", c.minimum);
    if (c.maximum !== undefined && value > c.maximum) throw new FieldError("maximum", c.maximum);
    return value;
  }

  // options: { provider: true (default) — ignore x-system fields; optional: [names] — treat as not required }
  // Returns { cleaned: {name: value|null}, errors: {name: message} }.
  function validate(record, options) {
    options = options || {};
    var provider = options.provider !== false;
    var optional = options.optional || [];
    var known = fields(false).map(function (f) { return f.name; });
    var cleaned = {};
    var errors = {};
    Object.keys(record).forEach(function (name) {
      if (known.indexOf(name) === -1) errors[name] = MESSAGES.unknown;
    });
    fields(provider).forEach(function (field) {
      var name = field.name;
      var raw = record[name];
      if (isMissing(raw)) {
        cleaned[name] = null;
        if ((field.constraints || {}).required && optional.indexOf(name) === -1) errors[name] = MESSAGES.required;
        return;
      }
      try {
        cleaned[name] = cleanValue(field, raw);
      } catch (e) {
        if (!(e instanceof FieldError)) throw e;
        errors[name] = e.message;
      }
    });
    return { cleaned: cleaned, errors: errors };
  }

  function enumLabel(name, code) {
    var field = schema().fields.filter(function (f) { return f.name === name; })[0];
    var labels = (field && field["x-enumLabels"]) || {};
    return labels[code] || code;
  }

  window.AedValidator = {
    validate: validate,
    fields: fields,
    enumLabel: enumLabel,
    MESSAGES: MESSAGES
  };
})();
