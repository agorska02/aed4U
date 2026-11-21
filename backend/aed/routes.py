from mcod.aed import views as aed_views

# Appended to `mcod.routes.routes` (see hackathon/integration/portal.patch); the "/{api_version}" variant is added there.
routes = [
    ("/aed-reports", aed_views.AedReportView()),
]
