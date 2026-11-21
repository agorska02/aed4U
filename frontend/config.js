// Prototype mode:
//   "mock" — in-browser mock of the API (api-mock.js), data in localStorage; works from file:// or any static host.
//   "api"  — real API under `apiBase`: the standalone demo server (serves its own config.js)
//            or the portal (hackathon/integration/config.portal.js is mounted in place of this file).
// demo: shows demo banner and demo accounts. adminPanelUrl: portal Administration Panel (portal mode only).
window.AED_CONFIG = { mode: "mock", apiBase: "/api", demo: true, adminPanelUrl: null };
