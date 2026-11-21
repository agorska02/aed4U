// Shared client (window.AedClient) + provider page logic.
// Transport depends on window.AED_CONFIG (config.js): "mock" → api-mock.js, "api" → fetch to the real API.
// Auth: token from POST /auth/login, sent as `Authorization: Bearer <token>` (same as the portal frontend).
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
      : "dane w lokalnej bazie SQLite serwera demo";
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
    initAuth: initAuth,
    handleAuthError: handleAuthError,
    showStatus: showStatus,
    hideStatus: hideStatus,
    setFieldError: setFieldError,
    clearErrors: clearErrors,
    applyApiErrors: applyApiErrors,
    errorMessage: errorMessage,
    statusBadge: statusBadge,
    STATUS_LABELS: STATUS_LABELS
  };

  setupDemo();

  // ---------------------------------------------------------------------------
  // Provider page (index.html)
  // ---------------------------------------------------------------------------
  var reportForm = $("aed-form");
  if (!reportForm) return;

  var REPORT_FIELDS = ["location_name", "data_date", "notes", "organization"];

  var adminLink = $("admin-link");
  if (config.adminPanelUrl) adminLink.href = config.adminPanelUrl;
  $("demo-resubmit-note").hidden = !config.demo;

  function renderReports(items) {
    var body = $("reports-body");
    body.textContent = "";
    $("reports-empty").hidden = items.length > 0;
    $("reports-table").hidden = items.length === 0;
    items.forEach(function (item) {
      var a = item.attributes || {};
      var row = document.createElement("tr");
      [a.location_name, a.organization_title, a.data_date, null, a.verification_comment || "–"].forEach(function (value, i) {
        var cell = document.createElement("td");
        if (i === 3) cell.appendChild(statusBadge(a.status)); else cell.textContent = value || "";
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
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

  var auth = initAuth({ onLogin: loadReports });

  reportForm.addEventListener("submit", function (event) {
    event.preventDefault();
    hideStatus();
    clearErrors(REPORT_FIELDS);

    var attributes = { location_name: reportForm.elements.location_name.value.trim() };
    if (reportForm.elements.notes.value.trim()) attributes.notes = reportForm.elements.notes.value.trim();
    if (reportForm.elements.data_date.value) attributes.data_date = reportForm.elements.data_date.value;

    if (!attributes.location_name) {
      setFieldError("location_name", "Podaj nazwę lokalizacji.");
      $("location_name").focus();
      showStatus("Formularz zawiera błędy. Popraw zaznaczone pola.", "error");
      return;
    }

    var button = reportForm.querySelector("button[type=submit]");
    button.disabled = true;
    api("POST", "/aed-reports", { data: { type: "aed_report", attributes: attributes } })
      .then(function (res) {
        if (handleAuthError(res, auth)) return;
        if (res.ok) {
          reportForm.reset();
          showStatus("Dziękujemy! Zgłoszenie zostało przesłane do weryfikacji.", "success");
          loadReports();
        } else if (res.status === 422) {
          applyApiErrors(res.body, REPORT_FIELDS);
          showStatus(errorMessage(res.body, "Formularz zawiera błędy. Popraw zaznaczone pola."), "error");
        } else {
          showStatus("Nie udało się wysłać zgłoszenia (błąd " + res.status + "). Spróbuj ponownie.", "error");
        }
      })
      .catch(function () { showStatus("Brak połączenia z serwerem.", "error"); })
      .finally(function () { button.disabled = false; });
  });
})();
