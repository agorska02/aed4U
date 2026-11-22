// Provider page: import many AED records from a CSV / XLSX / JSON / GeoJSON file (XLSX is sent in base64).
// Flow: choose a file -> dry run (POST /aed-report-imports, dry_run: true) -> report -> confirm -> import.
(function () {
  "use strict";

  var client = window.AedClient;
  var el = client.el;
  var $ = function (id) { return document.getElementById(id); };
  var form = $("import-form");
  if (!form) return;

  var report = $("import-report");
  var confirmButton = $("import-confirm");
  var pending = null; // {format, content} checked by the last dry run
  var MAX_LISTED_ERRORS = 50;
  var ACTION_LABELS = { create: "nowe", update: "aktualizacja", unchanged: "bez zmian" };

  if (client.config.demo) $("demo-import-files").hidden = false;

  function fieldTitle(name) {
    var field = window.AED_SCHEMA.fields.filter(function (f) { return f.name === name; })[0];
    return field ? field.title + " (" + name + ")" : name;
  }

  function formatOf(fileName) {
    var name = fileName.toLowerCase();
    if (/\.geojson$/.test(name)) return "geojson";
    if (/\.json$/.test(name)) return "json";
    if (/\.csv$/.test(name) || /\.txt$/.test(name)) return "csv";
    if (/\.xlsx$/.test(name)) return "xlsx";
    return null;
  }

  function base64(buffer) {
    var bytes = new Uint8Array(buffer);
    var chunks = [];
    for (var i = 0; i < bytes.length; i += 0x8000) {
      chunks.push(String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)));
    }
    return btoa(chunks.join(""));
  }

  // Text files as UTF-8 text; XLSX workbooks (zip) as base64.
  function readFile(file, format) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(format === "xlsx" ? base64(reader.result) : reader.result); };
      reader.onerror = function () { reject(reader.error); };
      if (format === "xlsx") reader.readAsArrayBuffer(file); else reader.readAsText(file, "utf-8");
    });
  }

  function summaryText(s) {
    return "Rekordy w pliku: " + s.rows + " · poprawne: " + s.valid + " · z błędami: " + s.invalid +
      " · nowe: " + s.create + " · aktualizacje: " + s.update + " · bez zmian: " + s.unchanged +
      " · możliwe duplikaty: " + s.duplicates;
  }

  function errorTable(errors) {
    var wrap = el("div", { className: "table-wrap" });
    var table = el("table", { className: "table" });
    var caption = el("caption", { className: "sr-only", text: "Błędy w pliku" });
    var head = el("thead");
    var headRow = el("tr");
    ["Wiersz", "Kolumna", "Błąd"].forEach(function (t) { headRow.appendChild(el("th", { scope: "col", text: t })); });
    head.appendChild(headRow);
    var body = el("tbody");
    errors.slice(0, MAX_LISTED_ERRORS).forEach(function (e) {
      var row = el("tr");
      [String(e.row), fieldTitle(e.field), e.message].forEach(function (t) { row.appendChild(el("td", { text: t })); });
      body.appendChild(row);
    });
    table.appendChild(caption);
    table.appendChild(head);
    table.appendChild(body);
    wrap.appendChild(table);
    return wrap;
  }

  function duplicateList(actions) {
    var list = el("ul");
    actions.forEach(function (a) {
      if (a.duplicate_of === null && a.duplicate_of_row === null) return;
      var target = a.duplicate_of_row !== null ? "wiersz " + a.duplicate_of_row + " tego pliku" : "urządzenie już zgłoszone w portalu";
      list.appendChild(el("li", {
        text: "Wiersz " + a.row + " – „" + (a.location_name || "") + "”: " + target + " (" + a.duplicate_distance_m + " m)"
      }));
    });
    return list.children.length ? list : null;
  }

  function actionsList(actions) {
    var list = el("ul");
    actions.forEach(function (a) {
      list.appendChild(el("li", { text: "Wiersz " + a.row + ": " + (a.location_name || "") + " – " + ACTION_LABELS[a.action] }));
    });
    return list;
  }

  function showReport(attrs) {
    report.textContent = "";
    report.hidden = false;
    var ok = attrs.status === "dry_run" || attrs.status === "imported";
    report.className = "import-report import-report--" + (ok ? "ok" : "error");

    var heading = {
      dry_run: "Plik jest poprawny",
      imported: "Import zakończony",
      rejected: "Plik zawiera błędy – nic nie zostało zapisane"
    }[attrs.status];
    report.appendChild(el("h3", { text: heading }));

    if (attrs.file_error) {
      report.appendChild(el("p", { text: attrs.file_error }));
    }
    if (attrs.summary) report.appendChild(el("p", { text: summaryText(attrs.summary) }));
    if (attrs.errors && attrs.errors.length) {
      report.appendChild(el("p", { text: "Popraw błędy w pliku i wyślij go ponownie" +
        (attrs.errors.length > MAX_LISTED_ERRORS ? " (pokazano " + MAX_LISTED_ERRORS + " z " + attrs.errors.length + ")" : "") + ":" }));
      report.appendChild(errorTable(attrs.errors));
    }
    var duplicates = attrs.actions && duplicateList(attrs.actions);
    if (duplicates) {
      report.appendChild(el("p", { text: "Możliwe duplikaty (w promieniu " + window.AedImport.DUPLICATE_RADIUS_M +
        " m, podobna nazwa lub ten sam adres) – administrator zdecyduje, który rekord zostaje:" }));
      report.appendChild(duplicates);
    }
    if (attrs.status === "dry_run" && attrs.actions && attrs.actions.length) {
      var details = el("details");
      details.appendChild(el("summary", { text: "Co zostanie zapisane" }));
      details.appendChild(actionsList(attrs.actions));
      report.appendChild(details);
    }
    if (attrs.status === "imported") {
      report.appendChild(el("p", { text: "Nowe i zmienione rekordy trafiły do weryfikacji przez administratora portalu." }));
    }
    report.focus();
  }

  function send(dryRun) {
    var payload = { data: { type: "aed_report_import", attributes: { format: pending.format, content: pending.content, dry_run: dryRun } } };
    return client.api("POST", "/aed-report-imports", payload).then(function (res) {
      if (client.handleAuthError(res, client.auth)) return null;
      if (res.status === 422) {
        client.setFieldError("import-file", client.errorMessage(res.body, "Nie udało się sprawdzić pliku."));
        return null;
      }
      if (!res.ok) {
        client.showStatus("Nie udało się przesłać pliku (błąd " + res.status + "). Spróbuj ponownie.", "error");
        return null;
      }
      return res.body.data.attributes;
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    client.hideStatus();
    client.setFieldError("import-file", null);
    confirmButton.hidden = true;
    report.hidden = true;
    var file = $("import-file").files[0];
    if (!file) {
      client.setFieldError("import-file", "Wybierz plik CSV, JSON lub GeoJSON.");
      $("import-file").focus();
      return;
    }
    var format = formatOf(file.name);
    if (!format) {
      client.setFieldError("import-file", /\.xls$/i.test(file.name)
        ? "To plik w starym formacie Excela (.xls). Zapisz go jako .xlsx albo .csv (UTF-8)."
        : "Nieobsługiwany typ pliku. Wybierz plik .csv, .xlsx, .json lub .geojson.");
      $("import-file").focus();
      return;
    }
    var button = form.querySelector("button[type=submit]");
    button.disabled = true;
    readFile(file, format)
      .then(function (content) {
        pending = { format: format, content: content };
        return send(true);
      })
      .then(function (attrs) {
        if (!attrs) return;
        showReport(attrs);
        var writable = attrs.summary ? attrs.summary.create + attrs.summary.update : 0;
        if (attrs.status === "dry_run" && writable > 0) {
          confirmButton.textContent = "Importuj (" + writable + ")";
          confirmButton.hidden = false;
        }
      })
      .catch(function () { client.showStatus("Nie udało się odczytać pliku albo połączyć z serwerem.", "error"); })
      .finally(function () { button.disabled = false; });
  });

  confirmButton.addEventListener("click", function () {
    if (!pending) return;
    confirmButton.disabled = true;
    send(false)
      .then(function (attrs) {
        if (!attrs) return;
        confirmButton.hidden = true;
        showReport(attrs);
        if (attrs.status === "imported") {
          form.reset();
          pending = null;
          client.reloadReports();
        }
      })
      .catch(function () { client.showStatus("Brak połączenia z serwerem.", "error"); })
      .finally(function () { confirmButton.disabled = false; });
  });
})();
