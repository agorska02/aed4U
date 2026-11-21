// Public view (mapa.html): verified AED devices from GET /aed-devices?format=geojson on a Leaflet map and in
// an equivalent, accessible list. The list works without the map (no internet / Leaflet blocked).
(function () {
  "use strict";

  var client = window.AedClient;
  var el = client.el;
  var $ = function (id) { return document.getElementById(id); };
  var Hours = window.AedHours;

  var POLAND = { center: [52.07, 19.48], zoom: 6 };
  var LIST_LIMIT = 200; // longer lists: narrow down with the search or "nearest"
  var STATUS_TEXT = { open: "dostępny teraz", closed: "teraz niedostępny", unknown: "godziny: brak danych" };

  var features = [];
  var userPosition = null;
  var map = null;
  var markers = {};
  var layer = null;

  // --- data ---
  function loadDevices() {
    if (client.config.mode === "mock") {
      return window.AedMockApi.request("GET", "/aed-devices?format=geojson").then(function (res) { return JSON.parse(res.body); });
    }
    return fetch(client.config.apiBase + "/aed-devices?format=geojson").then(function (resp) {
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      return resp.json();
    });
  }

  function availability(p, now) {
    if (p.device_status !== "operational") return "closed";
    return Hours.statusAt(p.opening_hours, now);
  }

  function matches(feature, query, filters, now) {
    var p = feature.properties;
    if (filters.openNow && availability(p, now) !== "open") return false;
    if (filters.allDay && String(p.opening_hours).trim() !== "24/7") return false;
    if (filters.publicOnly && p.access !== "public") return false;
    if (filters.pediatric && p.pediatric !== "yes") return false;
    if (!query) return true;
    var haystack = [p.location_name, buildingType(p), p.city, p.commune, p.street, p.postal_code, p.operator_name].join(" ").toLowerCase();
    return query.split(/\s+/).every(function (word) { return haystack.indexOf(word) !== -1; });
  }

  function distanceTo(feature) {
    if (!userPosition) return null;
    var c = feature.geometry.coordinates;
    return window.AedImport.distanceM(userPosition[0], userPosition[1], c[1], c[0]);
  }

  function formatDistance(metres) {
    if (metres === null) return "";
    return metres < 1000 ? Math.round(metres / 10) * 10 + " m" : (metres / 1000).toFixed(1).replace(".", ",") + " km";
  }

  // Polish plural: 1 defibrylator, 2–4 defibrylatory, 5+ defibrylatorów (12–14 too).
  function plural(n, one, few, many) {
    if (n === 1) return n + " " + one;
    var tens = n % 100, units = n % 10;
    return n + " " + (units >= 2 && units <= 4 && (tens < 12 || tens > 14) ? few : many);
  }

  function currentFilters() {
    return {
      openNow: $("f-open-now").checked,
      allDay: $("f-24h").checked,
      publicOnly: $("f-public").checked,
      pediatric: $("f-pediatric").checked
    };
  }

  // --- list ---
  function buildingType(p) {
    return p.building_type === "other" && p.building_type_other
      ? p.building_type_other
      : client.formatValue("building_type", p.building_type);
  }

  function deviceItem(feature, now) {
    var p = feature.properties;
    var c = feature.geometry.coordinates;
    var state = availability(p, now);
    var item = el("li", { className: "aed-item aed-item--" + state, id: "aed-" + feature.id });
    var title = el("h3", { className: "aed-item__title" });
    title.appendChild(document.createTextNode(p.location_name));
    var distance = formatDistance(distanceTo(feature));
    if (distance) title.appendChild(el("span", { className: "aed-item__distance", text: " · " + distance }));
    item.appendChild(title);
    item.appendChild(el("p", { className: "aed-item__where", text: buildingType(p) + " · " + p.location_description }));
    item.appendChild(el("p", { text: client.addressLine(p) }));

    var facts = el("ul", { className: "aed-item__facts" });
    var stateText = p.device_status !== "operational" ? client.formatValue("device_status", p.device_status) : STATUS_TEXT[state];
    facts.appendChild(el("li", { className: "aed-state aed-state--" + state, text: stateText }));
    facts.appendChild(el("li", { text: "Godziny: " + Hours.describe(p.opening_hours) }));
    facts.appendChild(el("li", { text: "Dostęp: " + client.formatValue("access", p.access) }));
    if (p.pediatric === "yes") facts.appendChild(el("li", { text: "Tryb dla dzieci" }));
    facts.appendChild(el("li", { text: p.indoor ? "Wewnątrz budynku" + (p.floor !== null && p.floor !== undefined ? ", kondygnacja " + p.floor : "") : "Na zewnątrz" }));
    item.appendChild(facts);
    if (p.access_notes) item.appendChild(el("p", { className: "hint", text: p.access_notes }));

    var actions = el("p", { className: "aed-item__actions" });
    if (map) {
      var show = el("button", { type: "button", className: "btn btn--small btn--secondary", text: "Pokaż na mapie" });
      show.addEventListener("click", function () { focusMarker(feature.id); });
      actions.appendChild(show);
    }
    var route = el("a", {
      className: "btn btn--small btn--secondary",
      href: "https://www.openstreetmap.org/directions?route=" + (userPosition ? userPosition.join(",") : "") + "%3B" + c[1] + "," + c[0],
      target: "_blank",
      rel: "noopener",
      text: "Trasa"
    });
    route.appendChild(el("span", { className: "sr-only", text: " do: " + p.location_name + " (otwiera się w nowej karcie)" }));
    actions.appendChild(route);
    item.appendChild(actions);
    item.appendChild(el("p", { className: "hint", text: "Dysponent: " + p.operator_name + " · dane na dzień " + p.data_date }));
    return item;
  }

  function render() {
    var now = new Date();
    var query = $("search").value.trim().toLowerCase();
    var filters = currentFilters();
    var visible = features.filter(function (f) { return matches(f, query, filters, now); });
    if (userPosition) visible.sort(function (a, b) { return distanceTo(a) - distanceTo(b); });
    else visible.sort(function (a, b) { return String(a.properties.city).localeCompare(String(b.properties.city), "pl"); });

    var list = $("aed-list");
    list.textContent = "";
    visible.slice(0, LIST_LIMIT).forEach(function (f) { list.appendChild(deviceItem(f, now)); });
    $("list-empty").hidden = visible.length > 0;
    var count = plural(visible.length, "defibrylator", "defibrylatory", "defibrylatorów");
    $("results-count").textContent = "Znaleziono: " + count +
      (visible.length > LIST_LIMIT ? " (na liście pierwsze " + LIST_LIMIT + " – zawęź wyszukiwanie)" : "") +
      (userPosition ? ", od najbliższego" : "") + ".";
    renderMarkers(visible, now);
  }

  // --- map ---
  function initMap() {
    if (!window.L) {
      showMapStatus("Mapa jest niedostępna (brak połączenia z serwerem map). Wszystkie defibrylatory są na liście.");
      $("map-layout").classList.add("map-layout--no-map");
      document.querySelector(".view-toggle").hidden = true;
      return;
    }
    map = window.L.map("map", { scrollWheelZoom: false }).setView(POLAND.center, POLAND.zoom);
    client.tileLayer().addTo(map);
    layer = window.L.layerGroup().addTo(map);
  }

  function icon(state) {
    return window.L.divIcon({
      className: "aed-marker aed-marker--" + state,
      html: '<span aria-hidden="true">AED</span>',
      iconSize: [36, 36],
      iconAnchor: [18, 18],
      popupAnchor: [0, -16]
    });
  }

  function renderMarkers(visible, now) {
    if (!map) return;
    layer.clearLayers();
    markers = {};
    var bounds = [];
    visible.forEach(function (f) {
      var p = f.properties;
      var c = f.geometry.coordinates;
      var state = availability(p, now);
      var marker = window.L.marker([c[1], c[0]], {
        icon: icon(state),
        title: p.location_name,
        alt: p.location_name + " – " + STATUS_TEXT[state],
        keyboard: true
      });
      var popup = el("div");
      popup.appendChild(el("strong", { text: p.location_name }));
      popup.appendChild(el("div", { text: p.location_description }));
      popup.appendChild(el("div", { text: Hours.describe(p.opening_hours) }));
      var link = el("a", { href: "#aed-" + f.id, text: "Szczegóły na liście" });
      link.addEventListener("click", function (event) {
        event.preventDefault();
        var item = $("aed-" + f.id);
        if (!item) return;
        setView("list");
        item.setAttribute("tabindex", "-1");
        item.focus();
      });
      popup.appendChild(link);
      marker.bindPopup(popup);
      marker.addTo(layer);
      markers[f.id] = marker;
      bounds.push([c[1], c[0]]);
    });
    if (userPosition) bounds.push(userPosition);
    if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }

  function focusMarker(id) {
    var marker = markers[id];
    if (!marker) return;
    setView("map");
    map.setView(marker.getLatLng(), 17);
    marker.openPopup();
  }

  function showMapStatus(text) {
    var box = $("map-status");
    box.textContent = text;
    box.hidden = !text;
  }

  // --- small screens: list / map toggle ---
  function setView(view) {
    $("map-layout").setAttribute("data-view", view);
    $("show-list").setAttribute("aria-pressed", String(view === "list"));
    $("show-map").setAttribute("aria-pressed", String(view === "map"));
    if (map) setTimeout(function () { map.invalidateSize(); }, 0);
  }

  // --- geolocation (only after the user asks) ---
  function locate() {
    if (!navigator.geolocation) {
      showMapStatus("Twoja przeglądarka nie udostępnia lokalizacji. Wpisz miejscowość w wyszukiwarce.");
      return;
    }
    $("locate-btn").disabled = true;
    showMapStatus("Ustalanie Twojej lokalizacji…");
    navigator.geolocation.getCurrentPosition(function (position) {
      userPosition = [position.coords.latitude, position.coords.longitude];
      $("locate-btn").disabled = false;
      showMapStatus("");
      if (map) window.L.circleMarker(userPosition, { radius: 8, color: "#003b78", fillOpacity: 0.8 }).addTo(map).bindTooltip("Twoja lokalizacja");
      render();
    }, function () {
      $("locate-btn").disabled = false;
      showMapStatus("Nie udało się ustalić lokalizacji (brak zgody lub sygnału). Wpisz miejscowość w wyszukiwarce.");
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
  }

  // --- wiring ---
  initMap();
  ["f-open-now", "f-24h", "f-public", "f-pediatric"].forEach(function (id) { $(id).addEventListener("change", render); });
  var searchTimer = null;
  $("search").addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(render, 200);
  });
  $("locate-btn").addEventListener("click", locate);
  $("show-list").addEventListener("click", function () { setView("list"); });
  $("show-map").addEventListener("click", function () { setView("map"); });
  Array.prototype.forEach.call(document.querySelectorAll("[data-export]"), function (button) {
    button.addEventListener("click", function () {
      client.downloadExport(button.getAttribute("data-export")).catch(function () {
        showMapStatus("Nie udało się pobrać zbioru.");
      });
    });
  });

  loadDevices().then(function (collection) {
    features = collection.features || [];
    var date = collection.metadata && collection.metadata.data_date;
    $("data-date").textContent = "dane na dzień " + (date || new Date().toISOString().slice(0, 10)) +
      ", " + plural(features.length, "zweryfikowane urządzenie", "zweryfikowane urządzenia", "zweryfikowanych urządzeń");
    render();
  }).catch(function () {
    showMapStatus("Nie udało się pobrać danych o defibrylatorach. Odśwież stronę.");
  });
})();
