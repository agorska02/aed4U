import datetime
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import mcod.lib.model_sanitization


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        # The FK only needs the Organization model, so depend on its first migration. Depending on the newest one
        # pulls organizations.0018 into the plan before counters, and that portal migration runs SQL reading the
        # counters tables without declaring the dependency (test DB creation then fails).
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AedReport",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="Identifier")),
                (
                    "source",
                    models.CharField(
                        choices=[("form", "Form"), ("import", "File import"), ("api", "API")],
                        default="form",
                        max_length=10,
                        verbose_name="Source",
                    ),
                ),
                ("source_id", models.CharField(blank=True, max_length=100, verbose_name="Identifier at the operator")),
                ("operator_name", mcod.lib.model_sanitization.SanitizedCharField(max_length=300, verbose_name="Operator")),
                ("operator_regon", models.CharField(blank=True, max_length=14, verbose_name="Operator REGON")),
                ("location_name", mcod.lib.model_sanitization.SanitizedCharField(max_length=300, verbose_name="Location name")),
                (
                    "location_description",
                    mcod.lib.model_sanitization.SanitizedCharField(max_length=300, verbose_name="Exact location"),
                ),
                ("indoor", models.BooleanField(verbose_name="Indoor")),
                ("floor", models.SmallIntegerField(blank=True, null=True, verbose_name="Floor")),
                ("voivodeship", models.CharField(blank=True, max_length=30, verbose_name="Voivodeship")),
                ("county", models.CharField(blank=True, max_length=100, verbose_name="County")),
                ("commune", models.CharField(max_length=100, verbose_name="Commune")),
                ("teryt_terc", models.CharField(blank=True, max_length=7, verbose_name="TERYT TERC code")),
                ("city", models.CharField(max_length=200, verbose_name="City")),
                ("teryt_simc", models.CharField(blank=True, max_length=7, verbose_name="TERYT SIMC code")),
                ("street_type", models.CharField(blank=True, max_length=10, verbose_name="Street type")),
                ("street", models.CharField(blank=True, max_length=200, verbose_name="Street")),
                ("street_number", models.CharField(max_length=20, verbose_name="Street number")),
                ("postal_code", models.CharField(max_length=6, verbose_name="Postal code")),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=8, verbose_name="Latitude")),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9, verbose_name="Longitude")),
                (
                    "access",
                    models.CharField(
                        choices=[
                            ("public", "Public"),
                            ("customers", "During opening hours of the building"),
                            ("private", "Staff only"),
                        ],
                        max_length=10,
                        verbose_name="Access",
                    ),
                ),
                ("opening_hours", models.CharField(max_length=255, verbose_name="Opening hours")),
                (
                    "access_notes",
                    mcod.lib.model_sanitization.SanitizedCharField(blank=True, max_length=500, verbose_name="Access notes"),
                ),
                (
                    "device_status",
                    models.CharField(
                        choices=[
                            ("operational", "Operational"),
                            ("out_of_service", "Temporarily out of service"),
                            ("removed", "Removed"),
                        ],
                        default="operational",
                        max_length=15,
                        verbose_name="Device status",
                    ),
                ),
                (
                    "pediatric",
                    models.CharField(
                        blank=True,
                        choices=[("yes", "Yes"), ("no", "No"), ("unknown", "Unknown")],
                        max_length=7,
                        verbose_name="Pediatric mode",
                    ),
                ),
                ("manufacturer", models.CharField(blank=True, max_length=100, verbose_name="Manufacturer")),
                ("model", models.CharField(blank=True, max_length=100, verbose_name="Model")),
                ("last_inspection_date", models.DateField(blank=True, null=True, verbose_name="Last inspection date")),
                ("electrodes_expiry_date", models.DateField(blank=True, null=True, verbose_name="Electrodes expiry date")),
                ("battery_expiry_date", models.DateField(blank=True, null=True, verbose_name="Battery expiry date")),
                ("contact_phone", models.CharField(blank=True, max_length=9, verbose_name="Contact phone")),
                ("contact_email", models.EmailField(blank=True, max_length=254, verbose_name="Contact e-mail")),
                ("data_date", models.DateField(default=datetime.date.today, verbose_name="Data date")),
                ("notes", mcod.lib.model_sanitization.SanitizedTextField(blank=True, verbose_name="Notes")),
                (
                    "possible_duplicate_distance_m",
                    models.PositiveIntegerField(blank=True, null=True, verbose_name="Distance to the possible duplicate (m)"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("submitted", "Submitted for verification"),
                            ("verified", "Verified"),
                            ("rejected", "Rejected"),
                        ],
                        default="draft",
                        max_length=10,
                        verbose_name="Status",
                    ),
                ),
                (
                    "verification_comment",
                    mcod.lib.model_sanitization.SanitizedTextField(blank=True, verbose_name="Verification comment"),
                ),
                ("verified_at", models.DateTimeField(blank=True, null=True, verbose_name="Verification date")),
                ("created", models.DateTimeField(auto_now_add=True, verbose_name="Creation date")),
                ("modified", models.DateTimeField(auto_now=True, verbose_name="Modification date")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="aed_reports_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created by",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="aed_reports_modified",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Modified by",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="aed_reports",
                        to="organizations.Organization",
                        verbose_name="Institution",
                    ),
                ),
                (
                    "possible_duplicate_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="possible_duplicates",
                        to="aed.AedReport",
                        verbose_name="Possible duplicate of",
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="aed_reports_verified",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Verified by",
                    ),
                ),
            ],
            options={
                "verbose_name": "AED availability report",
                "verbose_name_plural": "AED availability reports",
                "ordering": ("-created",),
            },
        ),
    ]
