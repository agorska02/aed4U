// "Is this AED available now?" from opening_hours — the OpenStreetMap subset accepted by the validator
// (backend/aed/validation.py): "24/7" or rules "[months] [days] times", e.g. "Mo-Fr 08:00-16:00; Sa 09:00-13:00",
// "Su off", "PH off" (Polish public holidays), "May-Sep 08:00-20:00" (season; closed outside it).
// Later rules override earlier ones for the dates they match (OSM semantics). Unparseable values give "unknown".
(function () {
  "use strict";

  var DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAY_LABELS = { Mo: "pn", Tu: "wt", We: "śr", Th: "czw", Fr: "pt", Sa: "sob", Su: "nd", PH: "święta" };
  var MONTH_LABELS = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
  var SPAN_RE = /^([01][0-9]|2[0-4]):([0-5][0-9])-([01][0-9]|2[0-4]):([0-5][0-9])$/;
  var ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];

  // "Mo-Fr,Su" with codes ["Mo".."Su"] -> [0,1,2,3,4,6] (wrapping ranges like "Fr-Mo" or "Nov-Feb" allowed);
  // null if invalid. Tokens listed in `extra` (e.g. "PH") are accepted and reported in result.extra.
  function parseList(text, codes, extra) {
    var items = [];
    var found = [];
    var ok = text.split(",").every(function (part) {
      if (extra && extra.indexOf(part) !== -1) { found.push(part); return true; }
      var range = part.split("-");
      var start = codes.indexOf(range[0]);
      var end = range.length === 2 ? codes.indexOf(range[1]) : start;
      if (start === -1 || end === -1 || range.length > 2) return false;
      for (var i = start; ; i = (i + 1) % codes.length) {
        if (items.indexOf(i) === -1) items.push(i);
        if (i === end) break;
      }
      return true;
    });
    return ok ? { items: items, extra: found } : null;
  }

  // -> {always: bool, rules: [{months: [0..11] | null, days: [0..6], holidays: bool, spans: [[startMin, endMin]]}]}
  // or null. A rule without a day selector applies to every day, holidays included.
  function parse(value) {
    var text = String(value || "").trim();
    if (text === "24/7") return { always: true, rules: [] };
    if (!text) return null;
    var rules = [];
    var ok = text.split(/; ?/).every(function (ruleText) {
      var tokens = ruleText.trim().split(" ");
      if (tokens.length > 3) return false;
      var timesText = tokens.pop();
      var rule = { months: null, days: ALL_DAYS, holidays: true, spans: [] };
      if (tokens.length) {
        var months = parseList(tokens[0], MONTHS);
        if (months) { rule.months = months.items; tokens.shift(); }
      }
      if (tokens.length) {
        var days = parseList(tokens.shift(), DAYS, ["PH"]);
        if (!days) return false;
        rule.days = days.items;
        rule.holidays = days.extra.length > 0;
      }
      if (tokens.length) return false;
      if (timesText !== "off" && timesText !== "closed") {
        var good = timesText.split(",").every(function (spanText) {
          var m = SPAN_RE.exec(spanText);
          if (!m) return false;
          rule.spans.push([Number(m[1]) * 60 + Number(m[2]), Number(m[3]) * 60 + Number(m[4])]);
          return true;
        });
        if (!good) return false;
      }
      rules.push(rule);
      return true;
    });
    return ok ? { always: false, rules: rules } : null;
  }

  // --- Polish public holidays (ustawa o dniach wolnych od pracy) ---
  function easterSunday(year) { // anonymous Gregorian algorithm
    var a = year % 19, b = Math.floor(year / 100), c = year % 100, d = Math.floor(b / 4), e = b % 4;
    var f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
    var i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
    var month = Math.floor((h + l - 7 * m + 114) / 31), day = ((h + l - 7 * m + 114) % 31) + 1;
    return new Date(year, month - 1, day);
  }

  var FIXED_HOLIDAYS = ["01-01", "01-06", "05-01", "05-03", "08-15", "11-01", "11-11", "12-25", "12-26"];
  var EASTER_OFFSETS = [0, 1, 49, 60]; // Easter Sunday and Monday, Pentecost, Corpus Christi

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function isPublicHoliday(date) {
    var key = pad(date.getMonth() + 1) + "-" + pad(date.getDate());
    if (FIXED_HOLIDAYS.indexOf(key) !== -1) return true;
    if (key === "12-24" && date.getFullYear() >= 2025) return true; // Christmas Eve, a holiday since 2025
    var easter = easterSunday(date.getFullYear());
    return EASTER_OFFSETS.some(function (offset) {
      var holiday = new Date(easter.getFullYear(), easter.getMonth(), easter.getDate() + offset);
      return holiday.getMonth() === date.getMonth() && holiday.getDate() === date.getDate();
    });
  }

  function dayIndex(date) { return (date.getDay() + 6) % 7; } // Monday = 0

  function matches(rule, date, holiday) {
    if (rule.months && rule.months.indexOf(date.getMonth()) === -1) return false;
    return rule.days.indexOf(dayIndex(date)) !== -1 || (rule.holidays && holiday);
  }

  // Spans that apply on a date (the last matching rule wins; no rule: closed).
  function spansFor(parsed, date) {
    var holiday = isPublicHoliday(date);
    var spans = [];
    parsed.rules.forEach(function (rule) {
      if (matches(rule, date, holiday)) spans = rule.spans;
    });
    return spans;
  }

  // "open" | "closed" | "unknown"
  function statusAt(value, date) {
    var parsed = parse(value);
    if (!parsed) return "unknown";
    if (parsed.always) return "open";
    var minute = date.getHours() * 60 + date.getMinutes();
    var open = spansFor(parsed, date).some(function (span) {
      if (span[1] > span[0]) return minute >= span[0] && minute < span[1];
      return minute >= span[0]; // crosses midnight: evening part today
    });
    if (!open) {
      // crosses midnight: morning part comes from yesterday's spans
      var yesterday = new Date(date.getFullYear(), date.getMonth(), date.getDate() - 1);
      open = spansFor(parsed, yesterday).some(function (span) { return span[1] < span[0] && minute < span[1]; });
    }
    return open ? "open" : "closed";
  }

  // Open all the time, all year: "24/7" or e.g. "Mo-Su 00:00-24:00".
  function isAlwaysOpen(value) {
    var parsed = parse(value);
    if (!parsed) return false;
    if (parsed.always) return true;
    return parsed.rules.length === 1 && !parsed.rules[0].months && parsed.rules[0].days.length === 7 &&
      parsed.rules[0].spans.length === 1 && parsed.rules[0].spans[0][0] === 0 && parsed.rules[0].spans[0][1] === 1440;
  }

  function label(list, labels, codes) {
    return list.split(",").map(function (part) {
      return part.split("-").map(function (code) {
        return labels ? labels[codes.indexOf(code)] : DAY_LABELS[code];
      }).join("–");
    }).join(", ");
  }

  // Human-readable Polish version, e.g. "pn–pt 08:00–16:00; sob, nd nieczynne", "maj–wrz: całą dobę".
  function describe(value) {
    var text = String(value || "").trim();
    if (text === "24/7") return "całodobowo (24/7)";
    if (!parse(text)) return text;
    var ruleTexts = text.split(/; ?/).map(function (r) { return r.trim(); });
    // the same season on every rule (as the form builds it) is written once: "maj–wrz: pn–pt …; sob …"
    var first = ruleTexts[0].split(" ");
    var season = first.length > 1 && parseList(first[0], MONTHS) && ruleTexts.every(function (r) {
      return r.split(" ").length > 1 && r.split(" ")[0] === first[0];
    }) ? first[0] : null;
    if (season) {
      return label(season, MONTH_LABELS, MONTHS) + ": " +
        describe(ruleTexts.map(function (r) { return r.slice(season.length + 1); }).join("; "));
    }
    return ruleTexts.map(function (ruleText) {
      var tokens = ruleText.split(" ");
      var times = tokens.pop();
      var timesText = times === "off" || times === "closed" ? "nieczynne"
        : times === "00:00-24:00" ? "całą dobę"
          : times.split(",").map(function (span) { return span.replace("-", "–"); }).join(", ");
      var prefix = "";
      if (tokens.length && parseList(tokens[0], MONTHS)) prefix = label(tokens.shift(), MONTH_LABELS, MONTHS) + ": ";
      var days = tokens.length ? label(tokens[0]) + " " : "";
      return prefix + days + timesText;
    }).join("; ");
  }

  window.AedHours = {
    parse: parse,
    statusAt: statusAt,
    describe: describe,
    isAlwaysOpen: isAlwaysOpen,
    isPublicHoliday: isPublicHoliday
  };
})();
