// Portal mode: real portal API behind the aed-frontend nginx proxy (/api → mcod-local-api:8000).
// Mounted by docker-compose.hackathon.yml in place of frontend/config.js.
window.AED_CONFIG = {
  mode: "api",
  apiBase: "/api",
  demo: false,
  adminPanelUrl: "http://localhost:8001/aed/aedreport/"
};
