import datetime
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils import Choices

from mcod.core.db.models import Model
from mcod.lib.model_sanitization import SanitizedCharField, SanitizedTextField


class AedReport(Model):
    """Report about an AED device, filled in by a data provider (editor of an institution) and verified by
    a portal administrator.

    AED columns follow the reference data scope (hackathon/schema/aed.schema.json); values are validated
    with mcod.aed.validation. Choice codes must match the schema enums (checked in tests/test_schema.py).
    Empty optional text is stored as "" (Django convention), published as an empty CSV cell.
    """

    STATUS = Choices(
        ("draft", _("Draft")),
        ("submitted", _("Submitted for verification")),
        ("verified", _("Verified")),
        ("rejected", _("Rejected")),
    )
    PROVIDER_EDITABLE_STATUSES = (STATUS.draft, STATUS.rejected)
    SOURCE = Choices(("form", _("Form")), ("import", _("File import")), ("api", _("API")))
    ACCESS = Choices(
        ("public", _("Public")),
        ("customers", _("During opening hours of the building")),
        ("private", _("Staff only")),
    )
    DEVICE_STATUS = Choices(
        ("operational", _("Operational")),
        ("out_of_service", _("Temporarily out of service")),
        ("removed", _("Removed")),
    )
    PEDIATRIC = Choices(("yes", _("Yes")), ("no", _("No")), ("unknown", _("Unknown")))

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name=_("Identifier"))
    organization = models.ForeignKey(
        "organizations.Organization",
        models.PROTECT,
        related_name="aed_reports",
        verbose_name=_("Institution"),
    )
    source = models.CharField(max_length=10, choices=SOURCE, default=SOURCE.form, verbose_name=_("Source"))
    source_id = models.CharField(max_length=100, blank=True, verbose_name=_("Identifier at the operator"))

    # operator
    operator_name = SanitizedCharField(max_length=300, verbose_name=_("Operator"))
    operator_regon = models.CharField(max_length=14, blank=True, verbose_name=_("Operator REGON"))
    # place
    location_name = SanitizedCharField(max_length=300, verbose_name=_("Location name"))
    location_description = SanitizedCharField(max_length=300, verbose_name=_("Exact location"))
    indoor = models.BooleanField(verbose_name=_("Indoor"))
    floor = models.SmallIntegerField(null=True, blank=True, verbose_name=_("Floor"))
    # address
    voivodeship = models.CharField(max_length=30, blank=True, verbose_name=_("Voivodeship"))
    county = models.CharField(max_length=100, blank=True, verbose_name=_("County"))
    commune = models.CharField(max_length=100, verbose_name=_("Commune"))
    teryt_terc = models.CharField(max_length=7, blank=True, verbose_name=_("TERYT TERC code"))
    city = models.CharField(max_length=200, verbose_name=_("City"))
    teryt_simc = models.CharField(max_length=7, blank=True, verbose_name=_("TERYT SIMC code"))
    street_type = models.CharField(max_length=10, blank=True, verbose_name=_("Street type"))
    street = models.CharField(max_length=200, blank=True, verbose_name=_("Street"))
    street_number = models.CharField(max_length=20, verbose_name=_("Street number"))
    postal_code = models.CharField(max_length=6, verbose_name=_("Postal code"))
    # position (WGS84)
    latitude = models.DecimalField(max_digits=8, decimal_places=6, verbose_name=_("Latitude"))
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name=_("Longitude"))
    # access
    access = models.CharField(max_length=10, choices=ACCESS, verbose_name=_("Access"))
    opening_hours = models.CharField(max_length=255, verbose_name=_("Opening hours"))
    access_notes = SanitizedCharField(max_length=500, blank=True, verbose_name=_("Access notes"))
    # device
    device_status = models.CharField(
        max_length=15, choices=DEVICE_STATUS, default=DEVICE_STATUS.operational, verbose_name=_("Device status")
    )
    pediatric = models.CharField(max_length=7, choices=PEDIATRIC, blank=True, verbose_name=_("Pediatric mode"))
    manufacturer = models.CharField(max_length=100, blank=True, verbose_name=_("Manufacturer"))
    model = models.CharField(max_length=100, blank=True, verbose_name=_("Model"))
    last_inspection_date = models.DateField(null=True, blank=True, verbose_name=_("Last inspection date"))
    electrodes_expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Electrodes expiry date"))
    battery_expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Battery expiry date"))
    # contact (institutional only)
    contact_phone = models.CharField(max_length=9, blank=True, verbose_name=_("Contact phone"))
    contact_email = models.EmailField(max_length=254, blank=True, verbose_name=_("Contact e-mail"))
    # currency
    data_date = models.DateField(default=datetime.date.today, verbose_name=_("Data date"))
    notes = SanitizedTextField(blank=True, verbose_name=_("Notes"))

    # duplicate detection across sources (set on create/import, decided by the administrator)
    possible_duplicate_of = models.ForeignKey(
        "self",
        models.SET_NULL,
        null=True,
        blank=True,
        related_name="possible_duplicates",
        verbose_name=_("Possible duplicate of"),
    )
    possible_duplicate_distance_m = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Distance to the possible duplicate (m)")
    )

    # verification workflow
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
