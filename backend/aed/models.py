import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils import Choices

from mcod.core.db.models import Model
from mcod.lib.model_sanitization import SanitizedCharField, SanitizedTextField


class AedReport(Model):
    """Report about availability of an AED device, filled in by a data provider (editor of an institution)
    and verified by a portal administrator.

    Skeleton: `location_name` and `notes` are placeholders — target AED columns (address in separate fields,
    WGS84 coordinates, availability) will be added later, see hackathon/README.md.
    """

    STATUS = Choices(
        ("draft", _("Draft")),
        ("submitted", _("Submitted for verification")),
        ("verified", _("Verified")),
        ("rejected", _("Rejected")),
    )
    PROVIDER_EDITABLE_STATUSES = (STATUS.draft, STATUS.rejected)

    organization = models.ForeignKey(
        "organizations.Organization",
        models.PROTECT,
        related_name="aed_reports",
        verbose_name=_("Institution"),
    )
    location_name = SanitizedCharField(max_length=300, verbose_name=_("Location name"))
    notes = SanitizedTextField(blank=True, verbose_name=_("Notes"))
    data_date = models.DateField(default=datetime.date.today, verbose_name=_("Data date"))

    status = models.CharField(max_length=10, choices=STATUS, default=STATUS.draft, verbose_name=_("Status"))
    verification_comment = SanitizedTextField(blank=True, verbose_name=_("Verification comment"))
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        null=True,
        blank=True,
        related_name="aed_reports_verified",
        verbose_name=_("Verified by"),
    )
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Verification date"))

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Creation date"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        null=True,
        blank=True,
        related_name="aed_reports_created",
        verbose_name=_("Created by"),
    )
    modified = models.DateTimeField(auto_now=True, verbose_name=_("Modification date"))
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        null=True,
        blank=True,
        related_name="aed_reports_modified",
        verbose_name=_("Modified by"),
    )

    class Meta:
        ordering = ("-created",)
        verbose_name = _("AED availability report")
        verbose_name_plural = _("AED availability reports")

    def __str__(self):
        return self.location_name

    @property
    def is_editable_by_provider(self):
        return self.status in self.PROVIDER_EDITABLE_STATUSES

    def submit(self, user):
        self.status = self.STATUS.submitted
        self.modified_by = user

    def set_verification(self, status, user, comment=None):
        self.status = status
        self.verified_by = user
        self.verified_at = timezone.now()
        if comment is not None:
            self.verification_comment = comment
