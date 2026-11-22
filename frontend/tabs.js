// Tabs of the provider page (WAI-ARIA tabs pattern, automatic activation): arrow keys, Home and End move
// between tabs; the selected tab is kept in the URL hash (#nowe, #import, #zgloszenia), so a refresh, a link
// or the browser's Back button opens the right tab.
(function () {
  "use strict";

  var list = document.querySelector("[role=tablist][data-tabs]");
  if (!list) return;
  var tabs = Array.prototype.slice.call(list.querySelectorAll("[role=tab]"));

  function panelOf(tab) { return document.getElementById(tab.getAttribute("aria-controls")); }
  function byName(name) { return tabs.filter(function (t) { return t.getAttribute("data-tab") === name; })[0]; }

  function select(tab, options) {
    options = options || {};
    tabs.forEach(function (t) {
      var selected = t === tab;
      t.setAttribute("aria-selected", selected ? "true" : "false");
      t.tabIndex = selected ? 0 : -1;
      panelOf(t).hidden = !selected;
    });
    if (options.focus) tab.focus();
    var hash = "#" + tab.getAttribute("data-tab");
    if (options.history && location.hash !== hash) history.pushState(null, "", hash);
  }

  function fromHash() {
    var tab = byName(location.hash.slice(1));
    select(tab || tabs[0]);
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener("click", function () { select(tab, { history: true }); });
    tab.addEventListener("keydown", function (event) {
      var target = null;
      if (event.key === "ArrowRight") target = tabs[(index + 1) % tabs.length];
      else if (event.key === "ArrowLeft") target = tabs[(index - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") target = tabs[0];
      else if (event.key === "End") target = tabs[tabs.length - 1];
      if (!target) return;
      event.preventDefault();
      select(target, { focus: true, history: true });
    });
  });
  window.addEventListener("hashchange", fromHash);
  window.addEventListener("popstate", fromHash);
  fromHash();

  window.AedTabs = { select: function (name) { var tab = byName(name); if (tab) select(tab, { history: true }); } };
})();
