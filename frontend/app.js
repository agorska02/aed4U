// Shared client (window.AedClient) + provider page logic.
// Transport depends on window.AED_CONFIG (config.js): "mock" → api-mock.js, "api" → fetch to the real API.
// Auth: token from POST /auth/login, sent as `Authorization: Bearer <token>` (same as the portal frontend).
// The report form and the report details are generated from window.AED_SCHEMA (aed-schema.js).
(function () {
  "use strict";

  var config = window.AED_CONFIG || { mode: "mock", apiBase: "/api", demo: true };
  var TOKEN_KEY = "aed.token";
  var USER_KEY = "aed.user";
  var STATUS_LABELS = {
    draft: "Szkic",
    submitted: "Przesłane do weryfikacji",
    verified: "Zweryfikowane",
    rejected: "Odrzucone"
  };
  var SOURCE_LABELS = { form: "Formularz", "import": "Import pliku", api: "Integracja (API)" };

  var $ = function (id) { return document.getElementById(id); };

  // --- storage (may be unavailable, e.g. private mode) ---
  function store(key, value) {
    try {
      if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value);
    } catch (e) { /* ignore */ }
  }
  function load(key) {
    try { return sessionStorage.getItem(key); } catch (e) { return null; }
  }

  // --- API transport ---
  function api(method, path, payload) {
    var token = load(TOKEN_KEY);
    if (config.mode === "mock") {
      return window.AedMockApi.request(method, path, payload, token);
    }
    var headers = { "Accept-Language": "pl", "X-API-VERSION": "1.4" };
    if (token) headers.Authorization = "Bearer " + token;
    if (payload) headers["Content-Type"] = "application/vnd.api+json";
    return fetch(config.apiBase + path, {
      method: method,
      headers: headers,
      body: payload ? JSON.stringify(payload) : undefined
    }).then(function (resp) {
      return resp.json().catch(function () { return null; }).then(function (body) {
        return { status: resp.status, ok: resp.ok, body: body };
      });
    });
  }

  // --- UI helpers ---
  function el(tag, props) {
    var node = document.createElement(tag);
    Object.keys(props || {}).forEach(function (key) {
      if (key === "text") node.textContent = props[key];
      else if (key === "className") node.className = props[key];
      else node.setAttribute(key, props[key]);
    });
    return node;
  }

  function showStatus(message, kind) {
    var box = $("global-status");
    box.textContent = message;
    box.className = "alert alert--" + kind;
    box.hidden = false;
  }
  function hideStatus() { $("global-status").hidden = true; }

  function setFieldError(name, message) {
    var input = $(name);
    var error = $(name + "-error");
    if (!error) return;
    if (input) {
      if (message) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
    }
    error.textContent = message || "";
    error.hidden = !message;
  }
  function clearErrors(names) { names.forEach(function (n) { setFieldError(n, null); }); }

  // mcod returns 422 with JSON:API errors; the field name is the last segment of source.pointer.
  function applyApiErrors(body, fields) {
    ((body && body.errors) || []).forEach(function (err) {
      var name = ((err.source && err.source.pointer) || "").split("/").pop();
      if (fields.indexOf(name) !== -1) setFieldError(name, err.detail || "Nieprawidłowa wartość.");
    });
  }

  function errorMessage(body, fallback) {
    var err = body && body.errors && body.errors[0];
    return (err && (err.detail || err.title)) || (body && body.description) || fallback;
  }

  // Error summary at the top of a form: links move focus to the fields.
  function showErrorSummary(summaryId, errors, labels) {
    var box = $(summaryId);
    var names = Object.keys(errors);
    box.textContent = "";
    box.hidden = names.length === 0;
    if (!names.length) return;
    box.appendChild(el("h3", { text: names.length === 1 ? "Popraw 1 błąd" : "Popraw błędy (" + names.length + ")" }));
    var list = el("ul");
    names.forEach(function (name) {
      var item = el("li");
      var text = (labels[name] || name) + ": " + errors[name];
      var targetId = $(name) ? name : $(name + "-true") ? name + "-true" : null; // booleans are radio groups
      if (targetId) {
        var link = el("a", { href: "#" + targetId, text: text });
        link.addEventListener("click", function (event) {
          event.preventDefault();
          $(targetId).focus();
        });
        item.appendChild(link);
      } else {
        item.textContent = text;
      }
      list.appendChild(item);
    });
    box.appendChild(list);
    box.focus();
  }

  function schemaField(name) {
    return window.AED_SCHEMA.fields.filter(function (f) { return f.name === name; })[0];
  }

  function formatValue(name, value) {
    if (value === null || value === undefined || value === "") return "";
    var field = schemaField(name);
    if (field && field.type === "boolean") return value ? "tak" : "nie";
    if (field && field["x-enumLabels"]) return field["x-enumLabels"][value] || value;
    return String(value);
  }

  // <details> with all filled-in AED attributes, grouped like the form.
  function renderDetails(attrs) {
    var details = el("details", { className: "report-details" });
    details.appendChild(el("summary", { text: "Szczegóły" }));
    window.AED_SCHEMA["x-groups"].forEach(function (group) {
      var list = el("dl");
      window.AED_SCHEMA.fields.forEach(function (field) {
        if (field["x-group"] !== group.name) return;
        var text = formatValue(field.name, attrs[field.name]);
        if (!text) return;
        list.appendChild(el("dt", { text: field.title + (field["x-internal"] ? " (widoczne tylko dla administratora)" : "") }));
        list.appendChild(el("dd", { text: text }));
      });
      if (!list.children.length) return;
      details.appendChild(el("p", { className: "report-details__group", text: group.title }));
      details.appendChild(list);
    });
    if (attrs.uuid) {
      details.appendChild(el("p", { className: "hint", text: "Identyfikator: " + attrs.uuid + " · kanał: " + (attrs.source || "") }));
    }
    return details;
  }

  function addressLine(a) {
    var street = [a.street_type, a.street, a.street_number].filter(Boolean).join(" ");
    return [street, [a.postal_code, a.city].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  }

  function sourceLabel(source) { return SOURCE_LABELS[source] || source || ""; }

  // "Possible duplicate" note for a report (null if none).
  function duplicateNote(a) {
    var d = a.possible_duplicate;
    if (!d) return null;
    return el("p", {
      className: "duplicate-note",
      text: "Możliwy duplikat: „" + (d.location_name || "?") + "” (" + d.distance_m + " m)"
    });
  }

  // Public dataset download (verified records). Mock mode builds the file in the browser.
  function downloadExport(format) {
    if (config.mode !== "mock") {
      window.location.href = config.apiBase + "/aed-devices?format=" + encodeURIComponent(format);
      return Promise.resolve();
    }
    return api("GET", "/aed-devices?format=" + encodeURIComponent(format)).then(function (res) {
      var blob = new Blob([res.body], { type: res.contentType });
      var link = el("a", { href: URL.createObjectURL(blob), download: res.filename });
      document.body.appendChild(link);
      link.click();
      setTimeout(function () { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
    });
  }

  // Base map layer shared by the public map and the provider's location picker.
  // tile.openstreetmap.org requires a Referer (tile usage policy), which browsers do not send from file://
  // pages (Chrome then gets "Access blocked" tiles) — so file:// pages use the Humanitarian OSM style hosted by
  // OpenStreetMap France (same OSM data, served without a Referer; checked 2026-11-21).
  var OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">autorzy OpenStreetMap</a>';

  function tileLayer() {
    if (window.location.protocol === "file:") {
      return window.L.tileLayer("https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", {
        subdomains: "abc",
        maxZoom: 19,
        attribution: OSM_ATTRIBUTION + ', styl: <a href="https://www.hotosm.org/">Humanitarian OpenStreetMap Team</a>,' +
          ' serwer: <a href="https://openstreetmap.fr/">OpenStreetMap France</a>'
      });
    }
    return window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution: OSM_ATTRIBUTION
    });
  }

  function statusBadge(status) {
    var badge = document.createElement("span");
    badge.className = "badge badge--" + status;
    badge.textContent = STATUS_LABELS[status] || status;
    return badge;
  }

  function currentUser() {
    try { return JSON.parse(load(USER_KEY) || "null"); } catch (e) { return null; }
  }

  // --- demo banner & accounts ---
  function setupDemo() {
    var banner = $("demo-banner");
    if (!banner || !config.demo) return;
    banner.hidden = false;
    $("demo-mode").textContent = config.mode === "mock"
      ? "dane zapisywane tylko w tej przeglądarce"
      : "dane w bazie " + (config.database || "SQLite") + " serwera demo";
    var resetBtn = $("demo-reset");
    if (config.mode === "mock") {
      resetBtn.hidden = false;
      resetBtn.addEventListener("click", function () {
        window.AedMockApi.reset();
        store(TOKEN_KEY, null);
        store(USER_KEY, null);
        window.location.reload();
      });
    }
    var accounts = $("demo-accounts");
    if (accounts) accounts.hidden = false;
  }

  // --- auth (shared by provider and admin pages) ---
  // options: { onLogin(user), onLogout(), requireRole: "admin" | undefined }
  function initAuth(options) {
    var loginForm = $("login-form");

    function showLoggedIn(user) {
      $("login-section").hidden = true;
      $("app-section").hidden = false;
      $("user-bar").hidden = false;
      $("user-email").textContent = user.email || "";
      options.onLogin(user);
    }
    function showLoggedOut() {
      store(TOKEN_KEY, null);
      store(USER_KEY, null);
      $("login-section").hidden = false;
      $("app-section").hidden = true;
      $("user-bar").hidden = true;
      if (options.onLogout) options.onLogout();
    }

    loginForm.addEventListener("submit", function (event) {
      event.preventDefault();
      hideStatus();
      clearErrors(["email", "password"]);
      var email = loginForm.elements.email.value.trim();
      var password = loginForm.elements.password.value;
      if (!email) setFieldError("email", "Podaj adres e-mail.");
      if (!password) setFieldError("password", "Podaj hasło.");
      if (!email || !password) return;

      var button = loginForm.querySelector("button[type=submit]");
      button.disabled = true;
      api("POST", "/auth/login", { data: { type: "user", attributes: { email: email, password: password } } })
        .then(function (res) {
          var attrs = res.ok && res.body && res.body.data && res.body.data.attributes;
          if (!attrs || !attrs.token) {
            showStatus(errorMessage(res.body, "Nieprawidłowy e-mail lub hasło."), "error");
            return;
          }
          var user = { email: attrs.email || email, roles: attrs.roles || null };
          if (options.requireRole && user.roles && user.roles.indexOf(options.requireRole) === -1) {
            showStatus("To konto nie ma uprawnień administratora.", "error");
            return;
          }
          store(TOKEN_KEY, attrs.token);
          store(USER_KEY, JSON.stringify(user));
          loginForm.reset();
          showLoggedIn(user);
        })
        .catch(function () { showStatus("Brak połączenia z serwerem.", "error"); })
        .finally(function () { button.disabled = false; });
    });

    $("logout-btn").addEventListener("click", function () {
      api("POST", "/auth/logout").then(null, function () { /* ignore */ }).then(function () {
        showLoggedOut();
        showStatus("Wylogowano.", "success");
      });
    });

    var user = currentUser();
    var hasRequiredRole = !options.requireRole || !user || !user.roles || user.roles.indexOf(options.requireRole) !== -1;
    if (load(TOKEN_KEY) && user && hasRequiredRole) {
      showLoggedIn(user);
    } else if (user && !hasRequiredRole) {
      // Logged in as a provider: keep that session for index.html, just ask for an admin login here.
      $("login-section").hidden = false;
      $("app-section").hidden = true;
      showStatus("Zalogowano jako " + user.email + ". Ta strona wymaga konta administratora.", "info");
    } else {
      showLoggedOut();
    }

    return { logout: showLoggedOut };
  }

  function handleAuthError(res, auth) {
    if (res.status === 401) {
      auth.logout();
      showStatus("Sesja wygasła. Zaloguj się ponownie.", "error");
      return true;
    }
    if (res.status === 403) {
      showStatus("Twoje konto nie ma wymaganych uprawnień. Napisz na kontakt@dane.gov.pl.", "error");
      return true;
    }
    return false;
  }

  window.AedClient = {
    config: config,
    api: api,
    el: el,
    initAuth: initAuth,
    handleAuthError: handleAuthError,
    showStatus: showStatus,
    hideStatus: hideStatus,
    setFieldError: setFieldError,
    clearErrors: clearErrors,
    applyApiErrors: applyApiErrors,
    errorMessage: errorMessage,
    showErrorSummary: showErrorSummary,
    formatValue: formatValue,
    renderDetails: renderDetails,
    addressLine: addressLine,
    statusBadge: statusBadge,
    sourceLabel: sourceLabel,
    duplicateNote: duplicateNote,
    downloadExport: downloadExport,
    tileLayer: tileLayer,
    STATUS_LABELS: STATUS_LABELS
  };

  setupDemo();

  // ---------------------------------------------------------------------------
  // Provider page (index.html)
  // ---------------------------------------------------------------------------
  var reportForm = $("aed-form");
  if (!reportForm) return;

  var FORM_FIELDS = window.AedValidator.fields(true);
  var LABELS = { organization: "Instytucja" };
  FORM_FIELDS.forEach(function (f) { LABELS[f.name] = f.title; });

  // x-from-institution fields are not in the form: the server always takes them from the institution profile
  // (GET /auth/user shows them read-only). Profile keys of GET /auth/user for those fields:
  var INSTITUTION_KEYS = { operator_name: "title", operator_regon: "regon", contact_phone: "phone", contact_email: "email" };
  var INSTITUTION_FIELDS = window.AED_SCHEMA.fields.filter(function (f) { return f["x-from-institution"]; });
  var DEFAULTS = {
    device_status: function () { return "operational"; },
    data_date: function () { return new Date().toISOString().slice(0, 10); }
  };
  // WCAG 1.3.5 (identify input purpose) for fields with an autocomplete token.
  var AUTOCOMPLETE = {
    postal_code: "postal-code",
    city: "address-level2"
  };
  var SHORT_FIELDS = ["floor", "street_type", "street_number", "postal_code",
    "latitude", "longitude", "internal_contact_phone"];
  var PLACEHOLDERS = { latitude: "np. 50.061389", longitude: "np. 19.938333", postal_code: "np. 31-004" };

  var adminLink = $("admin-link");
  if (config.adminPanelUrl) adminLink.href = config.adminPanelUrl;
  $("demo-resubmit-note").hidden = !config.demo;

  // x-requiredIf fields are shown (and then required) only when the other field has the given value.
  function isRequired(field) {
    return !!(field.constraints || {}).required || !!field["x-requiredIf"];
  }

  function setupConditionalFields() {
    FORM_FIELDS.forEach(function (field) {
      var condition = field["x-requiredIf"];
      if (!condition) return;
      var other = Object.keys(condition)[0];
      var control = reportForm.elements[other];
      var wrapper = $(field.name).closest(".field");
      var update = function () {
        var show = control.value === condition[other];
        wrapper.hidden = !show;
        if (!show) $(field.name).value = "";
      };
      control.addEventListener("change", update);
      reportForm.addEventListener("reset", function () { setTimeout(update, 0); });
      update();
    });
  }

  function labelContent(node, field) {
    node.appendChild(document.createTextNode(field.title + " "));
    if (isRequired(field)) {
      node.appendChild(el("span", { "aria-hidden": "true", text: "*" }));
      node.appendChild(el("span", { className: "sr-only", text: "(wymagane)" }));
    }
  }

  function hintText(field) {
    return field.description || "";
  }

  function buildInput(field) {
    var c = field.constraints || {};
    var input;
    if (c["enum"]) {
      input = el("select");
      input.appendChild(el("option", { value: "", text: "— wybierz —" }));
      c["enum"].forEach(function (code) {
        input.appendChild(el("option", { value: code, text: formatValue(field.name, code) }));
      });
    } else if (c.maxLength && c.maxLength > 300) {
      input = el("textarea", { rows: "3" });
    } else {
      var type = "text";
      if (field.type === "date") type = "date";
      else if (field.format === "email") type = "email";
      else if (/phone$/.test(field.name)) type = "tel";
      input = el("input", { type: type });
      if (field.type === "integer" || /phone$/.test(field.name)) input.setAttribute("inputmode", "numeric");
      if (field.type === "number") input.setAttribute("inputmode", "decimal");
      if (PLACEHOLDERS[field.name]) input.setAttribute("placeholder", PLACEHOLDERS[field.name]);
    }
    if (c.maxLength) input.setAttribute("maxlength", String(c.maxLength));
    input.setAttribute("autocomplete", AUTOCOMPLETE[field.name] || "off");
    return input;
  }

  function buildField(field) {
    var hintId = field.name + "-hint";
    var errorId = field.name + "-error";
    var short = SHORT_FIELDS.indexOf(field.name) !== -1;
    var wrapper = el("div", { className: "field" + (short ? " field--short" : "") });
    var hint = hintText(field) ? el("p", { id: hintId, className: "hint", text: hintText(field) }) : null;
    var error = el("p", { id: errorId, className: "field__error" });
    error.hidden = true;
    var describedBy = (hint ? hintId + " " : "") + errorId;

    if (field.type === "boolean") {
      var group = el("fieldset", { className: "radio-group", "aria-describedby": describedBy });
      var legend = el("legend");
      labelContent(legend, field);
      group.appendChild(legend);
      if (hint) group.appendChild(hint);
      [["true", "Tak"], ["false", "Nie"]].forEach(function (option) {
        var id = field.name + "-" + option[0];
        var item = el("div", { className: "radio" });
        item.appendChild(el("input", { type: "radio", id: id, name: field.name, value: option[0] }));
        item.appendChild(el("label", { "for": id, text: option[1] }));
        group.appendChild(item);
      });
      group.appendChild(error);
      wrapper.appendChild(group);
      return wrapper;
    }

    var label = el("label", { "for": field.name });
    labelContent(label, field);
    var input = buildInput(field);
    input.id = field.name;
    input.name = field.name;
    input.setAttribute("aria-describedby", describedBy);
    if (isRequired(field)) input.required = true;
    wrapper.appendChild(label);
    if (hint) wrapper.appendChild(hint);
    wrapper.appendChild(input);
    wrapper.appendChild(error);
    return wrapper;
  }

  function buildForm() {
    var container = $("aed-form-fields");
    window.AED_SCHEMA["x-groups"].forEach(function (group) {
      var section = el("fieldset", { className: "form-section" });
      section.appendChild(el("legend", { text: group.title }));
      if (group.description) section.appendChild(el("p", { className: "hint", text: group.description }));
      var fromInstitution = INSTITUTION_FIELDS.filter(function (f) { return f["x-group"] === group.name; });
      if (fromInstitution.length) {
        var box = el("dl", { className: "institution-info", "data-group": group.name });
        box.appendChild(el("dt", { text: "Z profilu instytucji" }));
        box.appendChild(el("dd", { text: "Wczytywanie…" }));
        section.appendChild(box);
      }
      FORM_FIELDS.forEach(function (field) {
        if (field["x-group"] === group.name) section.appendChild(buildField(field));
      });
      container.appendChild(section);
    });
  }

  function applyDefaults() {
    Object.keys(DEFAULTS).forEach(function (name) {
      reportForm.elements[name].value = DEFAULTS[name]();
    });
  }

  function collectValues() {
    var values = {};
    FORM_FIELDS.forEach(function (field) {
      var control = reportForm.elements[field.name];
      values[field.name] = control ? control.value : "";
    });
    return values;
  }

  function setRadioInvalid(name, invalid) {
    var radios = reportForm.querySelectorAll("input[type=radio][name='" + name + "']");
    Array.prototype.forEach.call(radios, function (radio) {
      if (invalid) radio.setAttribute("aria-invalid", "true"); else radio.removeAttribute("aria-invalid");
    });
  }

  function showFieldErrors(errors) {
    FORM_FIELDS.forEach(function (field) {
      setFieldError(field.name, errors[field.name] || null);
      if (field.type === "boolean") setRadioInvalid(field.name, !!errors[field.name]);
    });
    setFieldError("organization", errors.organization || null);
    showErrorSummary("form-error-summary", errors, LABELS);
  }

  function errorsFromApi(body) {
    var errors = {};
    ((body && body.errors) || []).forEach(function (err) {
      var name = ((err.source && err.source.pointer) || "").split("/").pop() || "form";
      errors[name] = err.detail || err.title || "Nieprawidłowa wartość.";
    });
    return errors;
  }

  function renderReports(items) {
    var body = $("reports-body");
    body.textContent = "";
    $("reports-empty").hidden = items.length > 0;
    $("reports-table").hidden = items.length === 0;
    items.forEach(function (item) {
      var a = item.attributes || {};
      var row = el("tr");
      var place = el("td");
      place.appendChild(el("strong", { text: a.location_name || "" }));
      place.appendChild(el("div", { className: "hint", text: addressLine(a) }));
      var note = duplicateNote(a);
      if (note) place.appendChild(note);
      place.appendChild(renderDetails(a));
      row.appendChild(place);
      row.appendChild(el("td", { text: sourceLabel(a.source) }));
      row.appendChild(el("td", { text: formatValue("device_status", a.device_status) }));
      row.appendChild(el("td", { text: a.data_date || "" }));
      var statusCell = el("td");
      statusCell.appendChild(statusBadge(a.status));
      row.appendChild(statusCell);
      row.appendChild(el("td", { text: a.verification_comment || "–" }));
      body.appendChild(row);
    });
  }

  // Read-only institution profile in the form sections (operator, public contact).
  function showInstitution(institution, count) {
    Array.prototype.forEach.call(document.querySelectorAll(".institution-info"), function (box) {
      box.textContent = "";
      var group = box.getAttribute("data-group");
      if (!institution) {
        box.appendChild(el("dt", { text: "Z profilu instytucji" }));
        box.appendChild(el("dd", { text: "Dane zostaną uzupełnione z profilu Twojej instytucji w portalu." }));
        return;
      }
      INSTITUTION_FIELDS.forEach(function (field) {
        if (field["x-group"] !== group) return;
        box.appendChild(el("dt", { text: field.title }));
        box.appendChild(el("dd", { text: institution[INSTITUTION_KEYS[field.name]] || "brak w profilu instytucji" }));
      });
      if (group === "operator" && count > 1) {
        box.appendChild(el("dd", { className: "hint", text: "Należysz do kilku instytucji – zgłoszenie dotyczy pierwszej z nich." }));
      }
    });
  }

  function loadInstitution() {
    api("GET", "/auth/user").then(function (res) {
      var institutions = res.ok && res.body && res.body.data && res.body.data.attributes.institutions;
      showInstitution(institutions && institutions.length ? institutions[0] : null, institutions ? institutions.length : 0);
    }).catch(function () { showInstitution(null, 0); });
  }

  function loadReports() {
    api("GET", "/aed-reports").then(function (res) {
      if (handleAuthError(res, auth)) return;
      if (!res.ok) {
        showStatus(errorMessage(res.body, "Nie udało się pobrać zgłoszeń."), "error");
        return;
      }
      renderReports((res.body && res.body.data) || []);
    }).catch(function () {
      showStatus("Brak połączenia z serwerem.", "error");
    });
  }

  buildForm();
  applyDefaults();
  setupConditionalFields();
  var auth = initAuth({ onLogin: function () { loadInstitution(); loadReports(); } });
  window.AedClient.reloadReports = loadReports;
  window.AedClient.auth = auth;

  reportForm.addEventListener("submit", function (event) {
    event.preventDefault();
    hideStatus();
    var result = window.AedValidator.validate(collectValues());
    showFieldErrors(result.errors);
    if (Object.keys(result.errors).length) return;

    // Send typed JSON values (numbers, booleans) and skip empty optional fields.
    var attributes = {};
    Object.keys(result.cleaned).forEach(function (name) {
      if (result.cleaned[name] !== null) attributes[name] = result.cleaned[name];
    });

    var button = reportForm.querySelector("button[type=submit]");
    button.disabled = true;
    api("POST", "/aed-reports", { data: { type: "aed_report", attributes: attributes } })
      .then(function (res) {
        if (handleAuthError(res, auth)) return;
        if (res.ok) {
          reportForm.reset();
          applyDefaults();
          showStatus("Dziękujemy! Zgłoszenie zostało przesłane do weryfikacji.", "success");
          $("global-status").scrollIntoView();
          loadReports();
        } else if (res.status === 422) {
          showFieldErrors(errorsFromApi(res.body));
        } else {
          showStatus("Nie udało się wysłać zgłoszenia (błąd " + res.status + "). Spróbuj ponownie.", "error");
        }
      })
      .catch(function () { showStatus("Brak połączenia z serwerem.", "error"); })
      .finally(function () { button.disabled = false; });
  });
})();
