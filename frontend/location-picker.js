// Provider form: pick latitude/longitude on a map (Leaflet + OpenStreetMap). Typing the coordinates stays
// the primary, fully accessible way; for keyboard users the map can be panned with arrow keys and the
// centre of the map used as the point.
(function () {
  "use strict";

  var client = window.AedClient;
  var el = client.el;
  var lat = document.getElementById("latitude");
  var lon = document.getElementById("longitude");
  if (!lat || !lon || !window.L) return; // no form or no map library (offline): manual entry only

  var POLAND = { center: [52.07, 19.48], zoom: 6 };
  var field = lon.closest(".field");
  var box = el("div", { className: "location-picker" });
  var toggle = el("button", {
    type: "button",
    className: "btn btn--small btn--secondary",
    "aria-expanded": "false",
    "aria-controls": "location-map-panel",
    text: "Wskaż położenie na mapie"
  });
  var panel = el("div", { id: "location-map-panel" });
  panel.hidden = true;
  var help = el("p", {
    className: "hint",
    id: "location-map-help",
    text: "Kliknij miejsce, w którym jest urządzenie – współrzędne wpiszą się same. Z klawiatury: przesuń mapę " +
      "strzałkami, przybliż klawiszem +, a potem użyj przycisku poniżej."
  });
  var centre = el("button", { type: "button", className: "btn btn--small btn--secondary", text: "Użyj środka mapy" });
  var mapNode = el("div", { className: "map", id: "location-map", "aria-describedby": "location-map-help" });
  var live = el("p", { className: "sr-only", role: "status", "aria-live": "polite" });
  panel.appendChild(help);
  panel.appendChild(centre);
  panel.appendChild(mapNode);
  box.appendChild(toggle);
  box.appendChild(panel);
  box.appendChild(live);
  field.parentNode.insertBefore(box, field.nextSibling);

  var map = null;
  var marker = null;

  function current() {
    var a = parseFloat(lat.value), b = parseFloat(lon.value);
    return isFinite(a) && isFinite(b) ? [a, b] : null;
  }

  function setPoint(latlng, announce) {
    lat.value = latlng.lat.toFixed(6);
    lon.value = latlng.lng.toFixed(6);
    [lat, lon].forEach(function (input) { input.dispatchEvent(new Event("input", { bubbles: true })); });
    if (marker) marker.setLatLng(latlng);
    else marker = window.L.marker(latlng, { title: "Położenie urządzenia", alt: "Położenie urządzenia" }).addTo(map);
    if (announce) live.textContent = "Ustawiono współrzędne " + lat.value + ", " + lon.value + ".";
  }

  function open() {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    if (!map) {
      map = window.L.map(mapNode, { scrollWheelZoom: false });
      client.tileLayer().addTo(map);
      map.on("click", function (event) { setPoint(event.latlng, true); });
    }
    var point = current();
    if (point) {
      map.setView(point, 17);
      setPoint({ lat: point[0], lng: point[1] }, false);
    } else {
      map.setView(POLAND.center, POLAND.zoom);
    }
    setTimeout(function () { map.invalidateSize(); }, 0);
  }

  toggle.addEventListener("click", function () {
    if (panel.hidden) {
      open();
    } else {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  });
  centre.addEventListener("click", function () { setPoint(map.getCenter(), true); });
})();
