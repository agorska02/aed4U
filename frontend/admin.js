// Administrator view: list all AED reports and verify / reject them.
// Works in demo modes (mock, standalone server) via PATCH /aed-reports/{id} — a demo-only extension.
// In portal mode verification is done in the Administration Panel, so this page only links there.
(function () {
  "use strict";

  var client = window.AedClient;
  var config = client.config;
  var $ = function (id) { return document.getElementById(id); };

  if (!config.demo) {
    $("portal-notice").hidden = false;
    $("login-section").hidden = true;
    if (config.adminPanelUrl) $("portal-admin-link").href = config.adminPanelUrl;
    return;
  }

  var reports = [];
  var filter = $("status-filter");
  var sourceFilter = $("source-filter");
  var duplicateFilter = $("duplicate-filter");

  function render() {
    var body = $("reports-body");
    body.textContent = "";
    var visible = reports.filter(function (item) {
      var a = item.attributes;
      return (!filter.value || a.status === filter.value) &&
        (!sourceFilter.value || a.source === sourceFilter.value) &&
        (!duplicateFilter.checked || !!a.possible_duplicate);
    });
    $("reports-empty").hidden = visible.length > 0;
    $("reports-table").hidden = visible.length === 0;

    visible.forEach(function (item) {
      var a = item.attributes;
      var row = document.createElement("tr");
      var place = document.createElement("td");
      place.appendChild(client.el("strong", { text: a.location_name || "" }));
      place.appendChild(client.el("div", { className: "hint", text: client.addressLine(a) }));
      var note = client.duplicateNote(a);
      if (note) {
        note.appendChild(document.createTextNode(" – sprawdź, czy to to samo urządzenie; duplikat odrzuć z komentarzem."));
        place.appendChild(note);
      }
      place.appendChild(client.renderDetails(a));
      row.appendChild(place);
      var orgCell = document.createElement("td");
      orgCell.appendChild(document.createTextNode(a.organization_title || ""));
      orgCell.appendChild(client.el("div", { className: "hint", text: client.sourceLabel(a.source) }));
      row.appendChild(orgCell);
      row.appendChild(client.el("td", { text: a.data_date || "" }));
      var statusCell = document.createElement("td");
      statusCell.appendChild(client.statusBadge(a.status));
      row.appendChild(statusCell);
      row.appendChild(a.status === "submitted" ? verificationCell(item) : commentCell(a));
      body.appendChild(row);
    });
  }

  function commentCell(a) {
    var cell = document.createElement("td");
    cell.textContent = a.verification_comment || (a.verified_at ? "Bez komentarza" : "–");
    return cell;
  }

  function verificationCell(item) {
    var cell = document.createElement("td");
    var fieldId = "comment-" + item.id;
    var label = document.createElement("label");
    label.htmlFor = fieldId;
    label.className = "sr-only";
    label.textContent = "Komentarz do zgłoszenia: " + item.attributes.location_name;
    var comment = document.createElement("textarea");
    comment.id = fieldId;
    comment.rows = 2;
    comment.maxLength = 3000;
    comment.placeholder = "Komentarz (wymagany przy odrzuceniu)";
    comment.className = "input-small";

    var actions = document.createElement("div");
    actions.className = "actions";
    actions.appendChild(actionButton("Zweryfikuj", "btn--primary", function () { verify(item, "verified", comment); }));
    actions.appendChild(actionButton("Odrzuć", "btn--danger", function () { verify(item, "rejected", comment); }));

    cell.appendChild(label);
    cell.appendChild(comment);
    cell.appendChild(actions);
    return cell;
  }

  function actionButton(text, modifier, onClick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn--small " + modifier;
    button.textContent = text;
    button.addEventListener("click", onClick);
    return button;
  }

  function verify(item, status, commentField) {
    client.hideStatus();
    var text = commentField.value.trim();
    if (status === "rejected" && !text) {
      commentField.setAttribute("aria-invalid", "true");
      commentField.focus();
      client.showStatus("Podaj powód odrzucenia w komentarzu.", "error");
      return;
    }
    var payload = { data: { type: "aed_report", id: item.id, attributes: { status: status, verification_comment: text } } };
    client.api("PATCH", "/aed-reports/" + item.id, payload).then(function (res) {
      if (client.handleAuthError(res, auth)) return;
      if (!res.ok) {
        client.showStatus(client.errorMessage(res.body, "Nie udało się zapisać weryfikacji."), "error");
        return;
      }
      client.showStatus(
        "Zgłoszenie „" + item.attributes.location_name + "” – " + client.STATUS_LABELS[status].toLowerCase() + ".",
        "success"
      );
      loadReports();
    }).catch(function () {
      client.showStatus("Brak połączenia z serwerem.", "error");
    });
  }

  function loadReports() {
    client.api("GET", "/aed-reports").then(function (res) {
      if (client.handleAuthError(res, auth)) return;
      if (!res.ok) {
        client.showStatus(client.errorMessage(res.body, "Nie udało się pobrać zgłoszeń."), "error");
        return;
      }
      reports = (res.body && res.body.data) || [];
      render();
    }).catch(function () {
      client.showStatus("Brak połączenia z serwerem.", "error");
    });
  }

  filter.addEventListener("change", render);
  sourceFilter.addEventListener("change", render);
  duplicateFilter.addEventListener("change", render);
  Array.prototype.forEach.call(document.querySelectorAll("[data-export]"), function (button) {
    button.addEventListener("click", function () {
      client.downloadExport(button.getAttribute("data-export")).catch(function () {
        client.showStatus("Nie udało się pobrać zbioru.", "error");
      });
    });
  });

  var auth = client.initAuth({ onLogin: loadReports, requireRole: "admin" });
})();
