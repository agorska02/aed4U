from functools import partial

import falcon
from django.apps import apps
from django.utils.translation import gettext_lazy as _

from mcod.aed.deserializers import CreateAedReportRequest
from mcod.aed.serializers import AedReportApiResponse
from mcod.core.api.handlers import CreateOneHdlr, RetrieveManyHdlr
from mcod.core.api.hooks import login_required
from mcod.core.api.views import JsonAPIView
from mcod.core.versioning import versioned
from mcod.organizations.models import Organization

PROVIDER_ROLES = ["editor", "admin"]


def _field_error(field, message):
    exc = falcon.HTTPUnprocessableEntity()
    exc.errors = {field: [message]}
    return exc


class AedReportView(JsonAPIView):
    @falcon.before(login_required, roles=PROVIDER_ROLES)
    @versioned
    def on_get(self, request, response, *args, **kwargs):
        self.handle(request, response, self.GET, *args, **kwargs)

    @falcon.before(login_required, roles=PROVIDER_ROLES)
    @versioned
    def on_post(self, request, response, *args, **kwargs):
        self.handle_post(request, response, self.POST, *args, **kwargs)

    class GET(RetrieveManyHdlr):
        """Reports of the institutions the user is assigned to (all reports for superusers)."""

        database_model = apps.get_model("aed", "AedReport")
        serializer_schema = partial(AedReportApiResponse, many=True)

        def _get_queryset(self, cleaned, *args, **kwargs):
            queryset = self.database_model.objects.select_related("organization")
            user = self.request.user
            if user.is_superuser:
                return queryset
            return queryset.filter(organization__in=user.organizations.all())

    class POST(CreateOneHdlr):
        deserializer_schema = CreateAedReportRequest
        database_model = apps.get_model("aed", "AedReport")
        serializer_schema = partial(AedReportApiResponse, many=False)

        def _get_data(self, cleaned, *args, **kwargs):
            data = cleaned["data"]["attributes"]
            user = self.request.user
            data["organization"] = self._get_organization(user, data.pop("organization", None))
            model = self.database_model
            self.response.context.data = model.objects.create(
                status=model.STATUS.submitted, created_by=user, modified_by=user, **data
            )

        @staticmethod
        def _get_organization(user, organization_id):
            organizations = Organization.objects.all() if user.is_superuser else user.organizations.all()
            if organization_id is not None:
                try:
                    return organizations.get(pk=organization_id)
                except Organization.DoesNotExist:
                    raise _field_error("organization", _("You are not assigned to this institution."))
            if not user.is_superuser and organizations.count() == 1:
                return organizations.get()
            raise _field_error("organization", _("Select the institution the report concerns."))
