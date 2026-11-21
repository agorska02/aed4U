// Provider form: opening hours chosen with controls instead of typed. The picker builds the OpenStreetMap
// opening_hours value used by the dataset and file imports (see aed-hours.js), e.g.
// "Mo-Fr 08:00-16:00; Sa,Su off; PH off" or "May-Sep 00:00-24:00", and writes it to a hidden input.
(function () {
  "use strict";

  var DAY_CODES = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  var MONTH_CODES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var MONTH_NAMES = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień",
    "październik", "listopad", "grudzień"];
  // Rows of the weekly table; "mo".."fr" are shown instead of "wd" when working days have different hours.
  var ROWS = [
    { key: "wd", title: "Dni robocze (pn–pt)", days: [0, 1, 2, 3, 4] },
    { key: "mo", title: "Poniedziałek", days: [0], split: true },
    { key: "tu", title: "Wtorek", days: [1], split: true },
    { key: "we", title: "Środa", days: [2], split: true },
    { key: "th", title: "Czwartek", days: [3], split: true },
    { key: "fr", title: "Piątek", days: [4], split: true },
    { key: "sa", title: "Sobota", days: [5] },
    { key: "su", title: "Niedziela", days: [6] },
    { key: "ph", title: "Święta", holidays: true }
  ];
  var MODES = [["hours", "w godzinach"], ["allday", "całą dobę"], ["off", "nieczynne"]];
  var DEFAULTS = { wd: ["hours", "08:00", "16:00"], sa: ["off"], su: ["off"], ph: ["sunday"] };

  function el(tag, props) {
    var node = document.createElement(tag);
    Object.keys(props || {}).forEach(function (key) {
      if (key === "text") node.textContent = props[key];
      else if (key === "className") node.className = props[key];
      else node.setAttribute(key, props[key]);
    });
    return node;
  }

  function option(select, value, text) { select.appendChild(el("option", { value: value, text: text })); }

  function checkbox(id, text) {
    var wrap = el("div", { className: "field--inline hours-picker__check" });
    var input = el("input", { type: "checkbox", id: id });
    wrap.appendChild(input);
    wrap.appendChild(el("label", { "for": id, text: text }));
    return { node: wrap, input: input };
  }

  function timeInput(id, labelText) {
    var wrap = el("span", { className: "hours-picker__time" });
    wrap.appendChild(el("label", { "for": id, text: labelText }));
    var input = el("input", { type: "time", id: id });
    wrap.appendChild(input);
    return { node: wrap, input: input };
  }

  // "Mo-Fr", "Sa,Su", "Mo,We-Fr" from sorted day indexes; all seven days give "Mo-Su".
  function daysExpr(days) {
    var parts = [];
    var start = 0;
    for (var i = 1; i <= days.length; i++) {
      if (i < days.length && days[i] === days[i - 1] + 1) continue;
      var run = days.slice(start, i);
      if (run.length >= 3) parts.push(DAY_CODES[run[0]] + "-" + DAY_CODES[run[run.length - 1]]);
      else run.forEach(function (d) { parts.push(DAY_CODES[d]); });
      start = i;
    }
    return parts.join(",");
  }

  // opts: {labelContent(node, field)}; returns {node, attach(), value(), validate()}.
  function create(field, opts) {
    var name = field.name;
    var wrapper = el("div", { className: "field hours-picker" });
    var errorId = name + "-error";
    var hintId = name + "-hint";
    var group = el("fieldset", { className: "radio-group", "aria-describedby": hintId + " " + errorId });
    var legend = el("legend");
    opts.labelContent(legend, field);
    group.appendChild(legend);
    group.appendChild(el("p", {
      id: hintId,
      className: "hint",
      text: "Kiedy można skorzystać z urządzenia. Godziny wybierz z listy lub wpisz; „do 00:00” oznacza do północy."
    }));

    // no name="opening_hours": form.elements["opening_hours"] must not mix it with the radio of that id
    var hidden = el("input", { type: "hidden", id: name + "-value" });
    group.appendChild(hidden);

    // the first radio carries the field id: error summary links and aria-invalid point at it
    var modes = {};
    [["always", name, "Całą dobę, 7 dni w tygodniu (także w święta)"],
      ["custom", name + "-custom", "W wybranych dniach i godzinach"]].forEach(function (m) {
      var item = el("div", { className: "radio" });
      var input = el("input", { type: "radio", id: m[1], name: name + "-mode", value: m[0] });
      item.appendChild(input);
      item.appendChild(el("label", { "for": m[1], text: m[2] }));
      group.appendChild(item);
      modes[m[0]] = input;
    });

    var custom = el("div", { className: "hours-picker__custom", id: name + "-custom-panel" });
    var split = checkbox(name + "-split", "Różne godziny w poszczególne dni robocze");
    custom.appendChild(split.node);

    var rows = {};
    ROWS.forEach(function (row) {
      var id = name + "-" + row.key;
      var box = el("fieldset", { className: "hours-row" });
      box.appendChild(el("legend", { className: "hours-row__title", text: row.title }));
      var modeId = id + "-mode";
      var modeWrap = el("span", { className: "hours-picker__mode" });
      modeWrap.appendChild(el("label", { "for": modeId, className: "sr-only", text: row.title + ": dostępność" }));
      var mode = el("select", { id: modeId });
      if (row.holidays) option(mode, "sunday", "jak w niedzielę");
      MODES.forEach(function (m) { option(mode, m[0], m[1]); });
      modeWrap.appendChild(mode);
      box.appendChild(modeWrap);

      var times = el("span", { className: "hours-row__times" });
      var from = timeInput(id + "-from", "od");
      var to = timeInput(id + "-to", "do");
      times.appendChild(from.node);
      times.appendChild(to.node);
      var breakTimes = el("span", { className: "hours-row__times hours-row__break" });
      breakTimes.appendChild(el("span", { className: "hours-row__break-label", text: "po przerwie" }));
      var from2 = timeInput(id + "-from2", "od");
      var to2 = timeInput(id + "-to2", "do");
      breakTimes.appendChild(from2.node);
      breakTimes.appendChild(to2.node);
      var toggle = el("button", { type: "button", className: "btn btn--small btn--secondary hours-row__toggle" });
      box.appendChild(times);
      box.appendChild(toggle);
      box.appendChild(breakTimes);
      custom.appendChild(box);
      rows[row.key] = { def: row, box: box, mode: mode, from: from.input, to: to.input, from2: from2.input, to2: to2.input,
        times: times, breakTimes: breakTimes, toggle: toggle, hasBreak: false };
      toggle.addEventListener("click", function () {
        var r = rows[row.key];
        r.hasBreak = !r.hasBreak;
        if (!r.hasBreak) { r.from2.value = ""; r.to2.value = ""; }
        update();
        (r.hasBreak ? r.from2 : r.toggle).focus();
      });
    });
    group.appendChild(custom);

    var season = checkbox(name + "-season", "Dostępne tylko w części roku (sezonowo)");
    group.appendChild(season.node);
    var seasonBox = el("div", { className: "hours-picker__season" });
    var months = {};
    [["from", "od miesiąca"], ["to", "do miesiąca (włącznie)"]].forEach(function (m) {
      var id = name + "-season-" + m[0];
      var wrap = el("span", { className: "hours-picker__time" });
      wrap.appendChild(el("label", { "for": id, text: m[1] }));
      var select = el("select", { id: id });
      MONTH_NAMES.forEach(function (monthName, i) { option(select, MONTH_CODES[i], monthName); });
      wrap.appendChild(select);
      seasonBox.appendChild(wrap);
      months[m[0]] = select;
    });
    group.appendChild(seasonBox);

    var preview = el("p", { className: "hours-picker__preview", role: "status", "aria-live": "polite" });
    group.appendChild(preview);
    var error = el("p", { id: errorId, className: "field__error" });
    error.hidden = true;
    group.appendChild(error);
    wrapper.appendChild(group);

    function rowSpec(key) {
      var r = rows[key];
      var spec = { kind: r.mode.value, row: r.def.title };
      if (spec.kind === "hours") {
        spec.spans = [[r.from.value, r.to.value]];
        if (r.hasBreak) spec.spans.push([r.from2.value, r.to2.value]);
      }
      return spec;
    }

    function specText(spec) {
      if (spec.kind === "off") return "off";
      if (spec.kind === "allday") return "00:00-24:00";
      return spec.spans.map(function (s) { return s[0] + "-" + (s[1] === "00:00" ? "24:00" : s[1]); }).join(",");
    }

    // Problem with the hours of a row, or null.
    function specError(spec) {
      if (spec.kind !== "hours") return null;
      var previousEnd = null;
      for (var i = 0; i < spec.spans.length; i++) {
        var from = spec.spans[i][0], to = spec.spans[i][1];
        var part = i ? " (po przerwie)" : "";
        if (!from || !to) return spec.row + part + ": podaj godzinę od i do.";
        var end = to === "00:00" ? "24:00" : to;
        if (end <= from) return spec.row + part + ": godzina „do” musi być późniejsza niż „od” (do północy – wybierz 00:00).";
        if (previousEnd && from < previousEnd) return spec.row + ": godziny po przerwie muszą zaczynać się po " + previousEnd + ".";
        previousEnd = end;
      }
      return null;
    }

    // -> {value, error}
    function build() {
      var seasonPrefix = "";
      if (season.input.checked) {
        var a = MONTH_CODES.indexOf(months.from.value), b = MONTH_CODES.indexOf(months.to.value);
        if ((b + 1) % 12 !== a) seasonPrefix = (a === b ? MONTH_CODES[a] : MONTH_CODES[a] + "-" + MONTH_CODES[b]) + " ";
      }
      if (modes.always.checked) return { value: seasonPrefix ? seasonPrefix + "00:00-24:00" : "24/7", error: null };
      if (!modes.custom.checked) return { value: "", error: "Wybierz, kiedy urządzenie jest dostępne." };

      var perDay = [];
      var specs = [];
      ROWS.forEach(function (row) {
        if (row.holidays || (row.split ? !split.input.checked : row.key === "wd" && split.input.checked)) return;
        var spec = rowSpec(row.key);
        specs.push(spec);
        row.days.forEach(function (d) { perDay[d] = spec; });
      });
      var holiday = rowSpec("ph");
      if (holiday.kind === "sunday") holiday = perDay[6];
      else specs.push(holiday);
      for (var i = 0; i < specs.length; i++) {
        var problem = specError(specs[i]);
        if (problem) return { value: "", error: problem };
      }
      var texts = perDay.map(specText);
      if (texts.concat(specText(holiday)).every(function (t) { return t === "off"; })) {
        return { value: "", error: "Zaznacz co najmniej jeden dzień, w którym urządzenie jest dostępne." };
      }

      // group days with the same hours, in the order of the week
      var groups = [];
      texts.forEach(function (text, day) {
        var found = groups.filter(function (g) { return g.text === text; })[0];
        if (found) found.days.push(day); else groups.push({ text: text, days: [day] });
      });
      var rules = groups.map(function (g) { return daysExpr(g.days) + " " + g.text; });
      // holidays: a separate last rule (overrides weekdays), unless every day already has the same hours
      var holidayText = specText(holiday);
      if (!(groups.length === 1 && groups[0].text === holidayText)) rules.push("PH " + holidayText);
      return { value: rules.map(function (r) { return seasonPrefix + r; }).join("; "), error: null };
    }

    function update() {
      custom.hidden = !modes.custom.checked;
      seasonBox.hidden = !season.input.checked;
      ROWS.forEach(function (row) {
        var r = rows[row.key];
        r.box.hidden = row.split ? !split.input.checked : row.key === "wd" && split.input.checked;
        var withHours = r.mode.value === "hours";
        r.times.hidden = !withHours;
        r.breakTimes.hidden = !withHours || !r.hasBreak;
        r.toggle.hidden = !withHours;
        r.toggle.textContent = r.hasBreak ? "Usuń przerwę" : "Dodaj przerwę";
        r.toggle.setAttribute("aria-label", (r.hasBreak ? "Usuń przerwę: " : "Dodaj przerwę: ") + row.title);
      });
      var result = build();
      hidden.value = result.value;
      preview.textContent = result.value
        ? "Podsumowanie: " + window.AedHours.describe(result.value) + "."
        : "";
    }

    function setRow(key, values) {
      var r = rows[key];
      r.mode.value = values[0];
      r.from.value = values[1] || "08:00";
      r.to.value = values[2] || "16:00";
      r.from2.value = "";
      r.to2.value = "";
      r.hasBreak = false;
    }

    function reset() {
      modes.always.checked = false;
      modes.custom.checked = false;
      split.input.checked = false;
      season.input.checked = false;
      months.from.value = "May";
      months.to.value = "Sep";
      ROWS.forEach(function (row) { setRow(row.key, DEFAULTS[row.key] || DEFAULTS.wd); });
      update();
    }

    // Switching to separate working days starts them from the common working-day hours.
    split.input.addEventListener("change", function () {
      if (!split.input.checked) return;
      var wd = rows.wd;
      ROWS.forEach(function (row) {
        if (!row.split) return;
        var r = rows[row.key];
        r.mode.value = wd.mode.value;
        r.from.value = wd.from.value;
        r.to.value = wd.to.value;
        r.from2.value = wd.from2.value;
        r.to2.value = wd.to2.value;
        r.hasBreak = wd.hasBreak;
      });
    });
    group.addEventListener("change", update);
    group.addEventListener("input", update);
    reset();

    return {
      node: wrapper,
      // call after the node is in the form (the reset listener needs it)
      attach: function () { hidden.form.addEventListener("reset", function () { setTimeout(reset, 0); }); },
      value: function () { return hidden.value; },
      validate: function () { return build().error; }
    };
  }

  window.AedHoursPicker = { create: create };
})();
