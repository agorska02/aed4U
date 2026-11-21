import datetime

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import mcod.lib.model_sanitization


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0025_auto_20251010_1248"),
    ]

    operations = [
        migrations.CreateModel(
            name="AedReport",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("location_name", mcod.lib.model_sanitization.SanitizedCharField(max_length=300, verbose_name="Location name")),
                ("notes", mcod.lib.model_sanitization.SanitizedTextField(blank=True, verbose_name="Notes")),
                ("data_date", models.DateField(default=datetime.date.today, verbose_name="Data date")),
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
