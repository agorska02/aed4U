// In-browser mock of the AED API — same contract as the standalone server (standalone/server.py)
// and the portal module (backend/aed): JSON:API bodies, bearer token, statuses, 401/403/409/422 errors.
// Records are validated with aed-validator.js against window.AED_SCHEMA; demo data = window.AED_EXAMPLES.
// Imports, duplicate detection and the public export use aed-import.js (same rules as backend/aed/importing.py).
// Data lives in localStorage (falls back to memory). Demo only: passwords are compared in plain text.
(function () {
  "use strict";

  var DB_KEY = "aed.mock.db.v3";
  var memoryDb = null;

  function nowIso() { return new Date().toISOString().replace(/\.\d{3}Z$/, "Z"); }

  // For each row of AED_EXAMPLES: organization id, verification status, comment (same as standalone/seed.py).
  var EXAMPLE_REPORTS = [
    [1, "verified", ""],
    [1, "submitted", ""],
    [2, "verified", ""],
    [2, "rejected", "Po wymianie elektrod uzupełnij nowy termin ważności."],
    [1, "submitted", ""]
  ];

  function uuid4() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === "x" ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  function newReport(id, cleaned, meta) {
    var report = { id: id };
    Object.keys(cleaned).forEach(function (name) { report[name] = cleaned[name]; });
    Object.keys(meta).forEach(function (name) { report[name] = meta[name]; });
    return report;
  }

  function seedDb() {
    var t = nowIso();
    var reports = (window.AED_EXAMPLES || []).map(function (row, index) {
      var seed = EXAMPLE_REPORTS[index] || [1, "submitted", ""];
      var verified = seed[1] === "verified" || seed[1] === "rejected";
      var cleaned = window.AedValidator.validate(row).cleaned;
      return newReport(index + 1, cleaned, {
        uuid: row.id, organization_id: seed[0], source: row.source, status: seed[1], verification_comment: seed[2],
        verified_by_id: verified ? 3 : null, verified_at: verified ? row.verified_at : null,
        created: t, created_by_id: seed[0], modified: t, modified_by_id: verified ? 3 : seed[0]
      });
    });
    return {
      seq: reports.length,
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
      reports: reports
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
  // 422 with one JSON:API error per field, like mcod.
  function fieldErrors(errors) {
    var list = Object.keys(errors).map(function (name) {
      return { status: "422", title: "Field error", detail: errors[name], source: { pointer: "/data/attributes/" + name } };
    });
    return { status: 422, ok: false, body: { errors: list } };
  }
  function ok(status, body) { return { status: status, ok: true, body: body }; }

  function attributesOf(payload, type) {
    var data = payload && payload.data;
    if (!data || data.type !== type || typeof data.attributes !== "object") return null;
    return data.attributes;
  }

  var META_ATTRIBUTES = ["uuid", "source", "status", "verification_comment", "verified_at", "created", "modified"];

  function serialize(db, r) {
    var org = db.organizations.filter(function (o) { return o.id === r.organization_id; })[0];
    var attributes = { organization_title: org ? org.title : "" };
    window.AedValidator.fields(true).forEach(function (f) {
      attributes[f.name] = r[f.name] === undefined ? null : r[f.name];
    });
    META_ATTRIBUTES.forEach(function (name) { attributes[name] = r[name]; });
    var duplicate = r.possible_duplicate_of_id
      ? db.reports.filter(function (d) { return d.id === r.possible_duplicate_of_id; })[0] : null;
    attributes.possible_duplicate = duplicate ? {
      id: String(duplicate.id), uuid: duplicate.uuid, location_name: duplicate.location_name,
      distance_m: r.possible_duplicate_distance_m
    } : null;
    return { type: "aed_report", id: String(r.id), attributes: attributes };
  }

  // Same rules as the portal view: explicit institution must be the user's, otherwise the only one.
  function resolveOrganization(db, user, requested) {
    var allowed = isAdmin(user) ? db.organizations.map(function (o) { return o.id; }) : user.organizations;
    if (requested !== undefined && requested !== null) {
      return allowed.indexOf(requested) === -1 ? { error: "Nie należysz do tej instytucji." } : { id: requested };
    }
    if (!isAdmin(user) && allowed.length === 1) return { id: allowed[0] };
    return { error: "Wybierz instytucję, której dotyczy zgłoszenie." };
  }

  function organizationTitle(db, id) {
    return db.organizations.filter(function (o) { return o.id === id; })[0].title;
  }

  function download(text, contentType, filename) {
    return { status: 200, ok: true, body: text, contentType: contentType, filename: filename };
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
      var record = {};
      Object.keys(attrs).forEach(function (name) { if (name !== "organization") record[name] = attrs[name]; });
      // operator_name defaults to the institution's name, so it is not required from the form
      var result = window.AedValidator.validate(record, { optional: ["operator_name"] });
      var errors = result.errors;

      var org = resolveOrganization(db, user, attrs.organization);
      if (org.error) errors.organization = org.error;
      if (Object.keys(errors).length) return fieldErrors(errors);

      var cleaned = result.cleaned;
      if (!cleaned.operator_name) cleaned.operator_name = organizationTitle(db, org.id);
      var duplicate = window.AedImport.findDuplicate(cleaned, db.reports, null);
      var t = nowIso();
      db.seq += 1;
      var report = newReport(db.seq, cleaned, {
        uuid: uuid4(), organization_id: org.id, source: "form", status: "submitted", verification_comment: "",
        verified_by_id: null, verified_at: null, created: t, created_by_id: user.id, modified: t, modified_by_id: user.id,
        possible_duplicate_of_id: duplicate.candidate ? duplicate.candidate.id : null,
        possible_duplicate_distance_m: duplicate.distance
      });
      db.reports.push(report);
      saveDb(db);
      return ok(201, { data: serialize(db, report) });
    },

    "POST /aed-report-imports": function (db, payload, token) {
      var auth = currentUser(db, token, ["editor", "admin"]);
      if (auth.error) return auth.error;
      var attrs = attributesOf(payload, "aed_report_import");
      if (!attrs) return error(422, "Field error", "Nieprawidłowa struktura zapytania.");
      var dryRun = attrs.dry_run === undefined ? true : attrs.dry_run;
      var errors = {};
      if (["csv", "json", "geojson"].indexOf(attrs.format) === -1) errors.format = "Dozwolone: csv, json, geojson.";
      if (typeof attrs.content !== "string" || !attrs.content.trim()) errors.content = "Dołącz zawartość pliku.";
      if (typeof dryRun !== "boolean") errors.dry_run = "Dozwolone wartości: true, false.";
      var org = resolveOrganization(db, auth.user, attrs.organization);
      if (org.error) errors.organization = org.error;
      if (Object.keys(errors).length) return fieldErrors(errors);

      var response = function (status, plan, fileError) {
        plan = plan || { errors: [], actions: [], summary: null };
        return ok(201, { data: { type: "aed_report_import", id: uuid4(), attributes: {
          status: status, format: attrs.format, file_error: fileError || null, summary: plan.summary, errors: plan.errors,
          actions: plan.actions.slice(0, 500).map(function (a) {
            return { row: a.row, action: a.action, location_name: a.values.location_name,
              duplicate_of: a.duplicate_of === null ? null : String(a.duplicate_of),
              duplicate_of_row: a.duplicate_of_row, duplicate_distance_m: a.duplicate_distance_m };
          })
        } } });
      };
      var rows;
      try {
        rows = window.AedImport.parseFile(attrs.content, attrs.format);
      } catch (e) {
        if (e instanceof window.AedImport.ImportFileError) return response("rejected", null, e.message);
        throw e;
      }
      var own = db.reports.filter(function (r) { return r.organization_id === org.id; });
      var plan = window.AedImport.planImport(rows, own, db.reports, organizationTitle(db, org.id));
      if (plan.errors.length) return response("rejected", plan);
      if (dryRun) return response("dry_run", plan);

      var t = nowIso();
      var createdForRow = {};
      plan.actions.forEach(function (a) {
        if (a.action === "unchanged") return;
        var duplicateId = a.duplicate_of_row !== null ? createdForRow[a.duplicate_of_row] || null : a.duplicate_of;
        var meta = { source: "import", status: "submitted", verification_comment: "", verified_by_id: null, verified_at: null,
          modified: t, modified_by_id: auth.user.id, possible_duplicate_of_id: duplicateId,
          possible_duplicate_distance_m: a.duplicate_distance_m };
        if (a.action === "create") {
          db.seq += 1;
          meta.uuid = uuid4();
          meta.organization_id = org.id;
          meta.created = t;
          meta.created_by_id = auth.user.id;
          db.reports.push(newReport(db.seq, a.values, meta));
          createdForRow[a.row] = db.seq;
        } else {
          var report = db.reports.filter(function (r) { return r.id === a.record_id; })[0];
          Object.keys(a.values).forEach(function (k) { report[k] = a.values[k]; });
          Object.keys(meta).forEach(function (k) { report[k] = meta[k]; });
        }
      });
      saveDb(db);
      return response("imported", plan);
    },

    // Public unified dataset: verified records only (format: "" = JSON:API, csv, json, geojson).
    "GET /aed-devices": function (db, payload, token, id, query) {
      var format = query.format || "";
      if (["", "csv", "json", "geojson"].indexOf(format) === -1) {
        return error(400, "400 Bad Request", "Dozwolone formaty: csv, json, geojson.");
      }
      var rows = db.reports.filter(function (r) { return r.status === "verified"; })
        .sort(function (a, b) { return a.id - b.id; })
        .map(window.AedImport.exportRecord);
      var dataDate = new Date().toISOString().slice(0, 10);
      var filename = "aed-" + dataDate + "." + format;
      if (format === "csv") return download(window.AedImport.toCsv(rows), "text/csv;charset=utf-8", filename);
      if (format === "geojson") {
        return download(JSON.stringify(window.AedImport.toGeojson(rows, dataDate), null, 1), "application/geo+json", filename);
      }
      if (format === "json") return download(JSON.stringify(window.AedImport.toJson(rows), null, 1), "application/json", filename);
      var data = window.AedImport.toJson(rows).map(function (row) { return { type: "aed_device", id: row.id, attributes: row }; });
      return ok(200, { data: data, meta: { count: data.length, data_date: dataDate } });
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
    var parts = path.split("?");
    var query = {};
    (parts[1] || "").split("&").forEach(function (pair) {
      if (!pair) return;
      var kv = pair.split("=");
      query[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || "");
    });
    var cleanPath = parts[0].replace(/^\/\d+\.\d+(?=\/)/, "");
    var detail = cleanPath.match(/^\/aed-reports\/(\d+)$/);
    var key = method + " " + (detail ? "/aed-reports/:id" : cleanPath);
    var handler = routes[key];
    var db = loadDb();
    var result = handler ? handler(db, payload, token, detail ? Number(detail[1]) : null, query) : error(404, "Not found");
    // Simulate network latency so loading states are visible.
    return new Promise(function (resolve) { setTimeout(function () { resolve(result); }, 150); });
  }

  function reset() {
    memoryDb = null;
    try { localStorage.removeItem(DB_KEY); } catch (e) { /* ignore */ }
  }

  window.AedMockApi = { request: request, reset: reset };
})();
