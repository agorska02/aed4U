// "Is this AED available now?" from opening_hours — the OpenStreetMap subset accepted by the validator
// (backend/aed/validation.py): "24/7" or rules "Mo-Fr 08:00-16:00; Sa 09:00-13:00", "Su off", "PH off".
// Later rules override earlier ones for the days they name (OSM semantics). Public holidays (PH) are not
// known here, so PH rules are ignored. Unparseable values give "unknown".
(function () {
  "use strict";

  var DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  var DAY_LABELS = { Mo: "pn", Tu: "wt", We: "śr", Th: "czw", Fr: "pt", Sa: "sob", Su: "nd", PH: "święta" };
  var RULE_RE = /^(?:([A-Za-z,-]+) )?(.+)$/;
  var SPAN_RE = /^([01][0-9]|2[0-4]):([0-5][0-9])-([01][0-9]|2[0-4]):([0-5][0-9])$/;

  // "Mo-Fr,Su" -> [0,1,2,3,4,6] (wrapping ranges like "Fr-Mo" allowed); null if invalid; "PH" -> [].
  function parseDays(text) {
    var days = [];
    var ok = text.split(",").every(function (part) {
      if (part === "PH") return true;
      var range = part.split("-");
      var start = DAYS.indexOf(range[0]);
      var end = range.length === 2 ? DAYS.indexOf(range[1]) : start;
      if (start === -1 || end === -1 || range.length > 2) return false;
      for (var i = start; ; i = (i + 1) % 7) {
        if (days.indexOf(i) === -1) days.push(i);
        if (i === end) break;
      }
      return true;
    });
    return ok ? days : null;
  }

  // -> {rules: [{days: [0..6], spans: [[startMin, endMin], ...]}], always: bool} or null
  function parse(value) {
    var text = String(value || "").trim();
    if (text === "24/7") return { always: true, rules: [] };
    if (!text) return null;
    var rules = [];
    var ok = text.split(/; ?/).every(function (ruleText) {
      var match = RULE_RE.exec(ruleText.trim());
      if (!match) return false;
      var daysText = match[1];
      var timesText = match[2];
      // "Mo-Fr" alone would be matched as times; days selector must be followed by times
      var days = daysText ? parseDays(daysText) : [0, 1, 2, 3, 4, 5, 6];
      if (!days) return false;
      var spans = [];
      if (timesText !== "off" && timesText !== "closed") {
        var good = timesText.split(",").every(function (spanText) {
          var m = SPAN_RE.exec(spanText);
          if (!m) return false;
          spans.push([Number(m[1]) * 60 + Number(m[2]), Number(m[3]) * 60 + Number(m[4])]);
          return true;
        });
        if (!good) return false;
      }
      rules.push({ days: days, spans: spans });
      return true;
    });
    return ok ? { always: false, rules: rules } : null;
  }

  function dayIndex(date) { return (date.getDay() + 6) % 7; } // Monday = 0

  // Spans that apply on a weekday (the last rule naming that day wins).
  function spansFor(parsed, day) {
    var spans = null;
    parsed.rules.forEach(function (rule) {
      if (rule.days.indexOf(day) !== -1) spans = rule.spans;
    });
    return spans || [];
  }

  // "open" | "closed" | "unknown"
  function statusAt(value, date) {
    var parsed = parse(value);
    if (!parsed) return "unknown";
    if (parsed.always) return "open";
    var day = dayIndex(date);
    var minute = date.getHours() * 60 + date.getMinutes();
    var open = spansFor(parsed, day).some(function (span) {
      if (span[1] > span[0]) return minute >= span[0] && minute < span[1];
      return minute >= span[0]; // crosses midnight: evening part today
    });
    if (!open) {
      // crosses midnight: morning part comes from yesterday's spans
      var yesterday = (day + 6) % 7;
      open = spansFor(parsed, yesterday).some(function (span) { return span[1] < span[0] && minute < span[1]; });
    }
    return open ? "open" : "closed";
  }

  // Human-readable Polish version, e.g. "pn–pt 08:00–16:00; sob 09:00–13:00", "całodobowo".
  function describe(value) {
    var text = String(value || "").trim();
    if (text === "24/7") return "całodobowo (24/7)";
    if (!parse(text)) return text;
    return text.split(/; ?/).map(function (rule) {
      return rule.replace(/\b(Mo|Tu|We|Th|Fr|Sa|Su|PH)\b/g, function (d) { return DAY_LABELS[d]; })
        .replace(/(\d)-(\d)/g, "$1–$2").replace(/([a-zśęą]+)-([a-zśęą]+)/g, "$1–$2")
        .replace(/\boff\b|\bclosed\b/g, "nieczynne");
    }).join("; ");
  }

  window.AedHours = { parse: parse, statusAt: statusAt, describe: describe };
})();
