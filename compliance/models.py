from datetime import date, timedelta

from django.conf import settings
from django.db import models

EXPIRING_WINDOW_DAYS = 30
AUDIT_PASS_SCORE = 70


# ---------------------------------------------------------------------------
# Reference data (loaded from fixtures/reference_data.json, shared by all orgs)
# ---------------------------------------------------------------------------
class Region(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Country(models.Model):
    iso_code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=100)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="countries")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Tenancy
# ---------------------------------------------------------------------------
class Organisation(models.Model):
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        VIEWER = "viewer", "Viewer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.ADMIN)

    def __str__(self):
        return f"{self.user.email} ({self.role})"


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------
class Supplier(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        BLOCKED = "blocked", "Blocked"

    class RiskLevel(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=200)
    email = models.EmailField()
    contact_name = models.CharField(max_length=200, blank=True)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="suppliers")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.LOW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organisation", "name"], name="unique_supplier_name_per_org"),
        ]

    def __str__(self):
        return self.name


class Certificate(models.Model):
    class CertificateType(models.TextChoices):
        GLOBALGAP = "globalgap", "GLOBALG.A.P."
        ISO_9001 = "iso_9001", "ISO 9001"
        ISO_14001 = "iso_14001", "ISO 14001"
        BRCGS = "brcgs", "BRCGS"
        ORGANIC_EU = "organic_eu", "EU Organic"
        FAIRTRADE = "fairtrade", "Fairtrade"

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="certificates")
    certificate_type = models.CharField(max_length=20, choices=CertificateType.choices)
    certificate_number = models.CharField(max_length=50)
    issue_date = models.DateField()
    expiry_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "certificate_number"], name="unique_certificate_number_per_supplier"
            ),
        ]

    @property
    def status(self) -> str:
        today = date.today()
        if self.expiry_date < today:
            return "expired"
        if self.expiry_date <= today + timedelta(days=EXPIRING_WINDOW_DAYS):
            return "expiring"
        return "valid"

    def __str__(self):
        return f"{self.get_certificate_type_display()} {self.certificate_number}"


class Audit(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="audits")
    audit_date = models.DateField()
    auditor = models.CharField(max_length=200)
    score = models.PositiveSmallIntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-audit_date"]

    @property
    def result(self) -> str:
        return "pass" if self.score >= AUDIT_PASS_SCORE else "fail"

    def __str__(self):
        return f"Audit {self.supplier} {self.audit_date}"
