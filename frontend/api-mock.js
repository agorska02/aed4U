// In-browser mock of the AED API — same contract as the standalone server (standalone/server.py)
// and the portal module (backend/aed): JSON:API bodies, bearer token, statuses, 401/403/409/422 errors.
// Data lives in localStorage (falls back to memory). Demo only: passwords are compared in plain text.
(function () {
  "use strict";

  var DB_KEY = "aed.mock.db.v1";
  var memoryDb = null;

  function nowIso() { return new Date().toISOString().replace(/\.\d{3}Z$/, "Z"); }
  function today() { return new Date().toISOString().slice(0, 10); }

  function seedDb() {
    var t = nowIso();
    return {
      seq: 3,
      organizations: [
        { id: 1, title: "Urząd Miasta Demo (instytucja A)" },
        { id: 2, title: "Szpital Demo (instytucja B)" }
      ],
      users: [
        { id: 1, email: "dostawca@demo.local", fullname: "Dostawca A", password: "Demo123!", roles: ["editor"], organizations: [1] },
        { id: 2, email: "dostawca2@demo.local", fullname: "Dostawca B", password: "Demo123!", roles: ["editor"], organizations: [2] },
        { id: 3, email: "admin@demo.local", fullname: "Administrator portalu", password: "Admin123!", roles: ["admin", "editor"], organizations: [] }
      ],
      sessions: {},
      reports: [
        { id: 3, organization_id: 2, location_name: "Szpital Demo – izba przyjęć", notes: "Wejście od ul. Szpitalnej", data_date: today(),
          status: "rejected", verification_comment: "Uzupełnij godziny dostępności.", verified_by_id: 3, verified_at: t,
          created: t, created_by_id: 2, modified: t, modified_by_id: 3 },
        { id: 2, organization_id: 1, location_name: "Urząd Miasta – parter", notes: "", data_date: today(),
          status: "verified", verification_comment: "", verified_by_id: 3, verified_at: t,
          created: t, created_by_id: 1, modified: t, modified_by_id: 3 },
        { id: 1, organization_id: 1, location_name: "Dworzec Centralny – hala główna", notes: "Przy kasach biletowych", data_date: today(),
          status: "submitted", verification_comment: "", verified_by_id: null, verified_at: null,
          created: t, created_by_id: 1, modified: t, modified_by_id: 1 }
      ]
    };
  }

  function loadDb() {
    try {
      var raw = localStorage.getItem(DB_KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) { /* storage unavailable — use memory */ }
    if (!memoryDb) memoryDb = seedDb();
    return memoryDb;
  }
  function saveDb(db) {
    memoryDb = db;
    try { localStorage.setItem(DB_KEY, JSON.stringify(db)); } catch (e) { /* ignore */ }
  }

  function error(status, title, detail, field) {
    var err = { status: String(status), title: title, detail: detail || title };
    if (field) err.source = { pointer: "/data/attributes/" + field };
    return { status: status, ok: false, body: { errors: [err] } };
  }
  function ok(status, body) { return { status: status, ok: true, body: body }; }

  function attributesOf(payload, type) {
    var data = payload && payload.data;
    if (!data || data.type !== type || typeof data.attributes !== "object") return null;
    return data.attributes;
  }

  function serialize(db, r) {
    var org = db.organizations.filter(function (o) { return o.id === r.organization_id; })[0];
    return {
      type: "aed_report",
      id: String(r.id),
      attributes: {
        organization_title: org ? org.title : "",
        location_name: r.location_name,
        notes: r.notes,
        data_date: r.data_date,
        status: r.status,
        verification_comment: r.verification_comment,
        verified_at: r.verified_at,
        created: r.created,
        modified: r.modified
      }
    };
  }

  function currentUser(db, token, roles) {
    var userId = token && db.sessions[token];
    var user = db.users.filter(function (u) { return u.id === userId; })[0];
    if (!user) return { error: error(401, "401 Unauthorized", "Missing or invalid authorization header") };
    var allowed = user.roles.some(function (role) { return roles.indexOf(role) !== -1; });
    if (!allowed) return { error: error(403, "403 Forbidden", "Additional permissions are required!") };
    return { user: user };
  }

  function isAdmin(user) { return user.roles.indexOf("admin") !== -1; }

  function visibleReports(db, user) {
    return db.reports.filter(function (r) { return isAdmin(user) || user.organizations.indexOf(r.organization_id) !== -1; });
  }

  function isValidDate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(value) && !isNaN(Date.parse(value));
  }

  var routes = {
    "POST /auth/login": function (db, payload) {
      var attrs = attributesOf(payload, "user") || {};
      var email = String(attrs.email || "").trim().toLowerCase();
      var user = db.users.filter(function (u) { return u.email === email && u.password === attrs.password; })[0];
      if (!user) return error(401, "401 Unauthorized", "Nieprawidłowy e-mail lub hasło.");
      var token = "mock-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      db.sessions[token] = user.id;
      saveDb(db);
      return ok(201, { data: { type: "user", id: String(user.id),
        attributes: { email: user.email, fullname: user.fullname, token: token, roles: user.roles } } });
    },

    "POST /auth/logout": function (db, payload, token) {
      delete db.sessions[token];
      saveDb(db);
      return ok(201, { data: { type: "logout", attributes: { is_logged_out: true } } });
    },

    "GET /aed-reports": function (db, payload, token) {
      var auth = currentUser(db, token, ["editor", "admin"]);
      if (auth.error) return auth.error;
      var data = visibleReports(db, auth.user)
        .sort(function (a, b) { return b.id - a.id; })
        .map(function (r) { return serialize(db, r); });
      return ok(200, { data: data, meta: { count: data.length } });
    },

    "POST /aed-reports": function (db, payload, token) {
      var auth = currentUser(db, token, ["editor", "admin"]);
      if (auth.error) return auth.error;
      var user = auth.user;
      var attrs = attributesOf(payload, "aed_report");
      if (!attrs) return error(422, "Field error", "Nieprawidłowa struktura zapytania.");
      var name = typeof attrs.location_name === "string" ? attrs.location_name.trim() : "";
      if (!name) return error(422, "Field error", "Pole wymagane.", "location_name");
      if (name.length > 300) return error(422, "Field error", "Maksymalnie 300 znaków.", "location_name");
      var notes = typeof attrs.notes === "string" ? attrs.notes.trim() : "";
      if (notes.length > 3000) return error(422, "Field error", "Maksymalnie 3000 znaków.", "notes");
      var dataDate = attrs.data_date || today();
      if (!isValidDate(dataDate)) return error(422, "Field error", "Data w formacie rrrr-mm-dd.", "data_date");

      var allowed = isAdmin(user) ? db.organizations.map(function (o) { return o.id; }) : user.organizations;
      var orgId = attrs.organization;
      if (orgId !== undefined && orgId !== null) {
        if (allowed.indexOf(orgId) === -1) return error(422, "Field error", "Nie należysz do tej instytucji.", "organization");
      } else if (!isAdmin(user) && allowed.length === 1) {
        orgId = allowed[0];
      } else {
        return error(422, "Field error", "Wybierz instytucję, której dotyczy zgłoszenie.", "organization");
      }

      var t = nowIso();
      db.seq += 1;
      var report = { id: db.seq, organization_id: orgId, location_name: name, notes: notes, data_date: dataDate,
        status: "submitted", verification_comment: "", verified_by_id: null, verified_at: null,
        created: t, created_by_id: user.id, modified: t, modified_by_id: user.id };
      db.reports.push(report);
      saveDb(db);
      return ok(201, { data: serialize(db, report) });
    },

    // Demo-only extension (in the portal, verification is done in the Administration Panel).
    "PATCH /aed-reports/:id": function (db, payload, token, id) {
      var auth = currentUser(db, token, ["admin"]);
      if (auth.error) return auth.error;
      var attrs = attributesOf(payload, "aed_report") || {};
      if (attrs.status !== "verified" && attrs.status !== "rejected") {
        return error(422, "Field error", "Dozwolone: verified, rejected.", "status");
      }
      var comment = typeof attrs.verification_comment === "string" ? attrs.verification_comment.trim() : "";
      if (attrs.status === "rejected" && !comment) {
        return error(422, "Field error", "Podaj powód odrzucenia.", "verification_comment");
      }
      var report = db.reports.filter(function (r) { return r.id === id; })[0];
      if (!report) return error(404, "Not found");
      if (report.status !== "submitted") {
        return error(409, "409 Conflict", "Można weryfikować tylko zgłoszenia przesłane do weryfikacji.");
      }
      var t = nowIso();
      report.status = attrs.status;
      report.verification_comment = comment;
      report.verified_by_id = auth.user.id;
      report.verified_at = t;
      report.modified = t;
      report.modified_by_id = auth.user.id;
      saveDb(db);
      return ok(202, { data: serialize(db, report) });
    }
  };

  function request(method, path, payload, token) {
    var cleanPath = path.replace(/^\/\d+\.\d+(?=\/)/, "");
    var detail = cleanPath.match(/^\/aed-reports\/(\d+)$/);
    var key = method + " " + (detail ? "/aed-reports/:id" : cleanPath);
    var handler = routes[key];
    var db = loadDb();
    var result = handler ? handler(db, payload, token, detail ? Number(detail[1]) : null) : error(404, "Not found");
    // Simulate network latency so loading states are visible.
    return new Promise(function (resolve) { setTimeout(function () { resolve(result); }, 150); });
  }

  function reset() {
    memoryDb = null;
    try { localStorage.removeItem(DB_KEY); } catch (e) { /* ignore */ }
  }

  window.AedMockApi = { request: request, reset: reset };
})();
