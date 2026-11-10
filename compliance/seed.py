"""Baseline seed data: test users and (optionally) sample suppliers.

Used by `manage.py seed` (make test-setup) and by POST /api/e2e/reset/.
Reference data (regions, countries) lives in fixtures/reference_data.json.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction

from .models import Audit, Certificate, Country, Organisation, Profile, Supplier

User = get_user_model()

DEFAULT_PASSWORD = "Password123!"
BASELINE_ORG = "Green Valley Foods"

# The accounts every test run can rely on. Keep emails stable; tests and the
# Postman environment use them.
BASELINE_USERS = [
    {"email": "admin@qa.test", "role": Profile.Role.ADMIN, "org": BASELINE_ORG},
    {"email": "viewer@qa.test", "role": Profile.Role.VIEWER, "org": BASELINE_ORG},
    # A user in a different organisation, for tenant-isolation tests.
    {"email": "other-admin@qa.test", "role": Profile.Role.ADMIN, "org": "Blue River Trading"},
]


def create_user(email: str, role: str, organisation: Organisation, password: str = DEFAULT_PASSWORD):
    user = User.objects.create_user(username=email.lower(), email=email.lower(), password=password)
    Profile.objects.create(user=user, organisation=organisation, role=role)
    return user


@transaction.atomic
def seed_users():
    orgs = {}
    for spec in BASELINE_USERS:
        org = orgs.get(spec["org"]) or Organisation.objects.filter(name=spec["org"]).first()
        if org is None:
            org = Organisation.objects.create(name=spec["org"])
        orgs[spec["org"]] = org
        if not User.objects.filter(username=spec["email"]).exists():
            create_user(spec["email"], spec["role"], org)
    return orgs


@transaction.atomic
def seed_sample_data():
    """A handful of realistic-looking suppliers for exploring the app by hand."""
    org = Organisation.objects.get(name=BASELINE_ORG)
    today = date.today()
    samples = [
        ("Sunrise Orchards", "NL", "active", "low"),
        ("Andes Fresh Produce", "PE", "active", "medium"),
        ("Cape Citrus Growers", "ZA", "active", "high"),
        ("Rhine Valley Dairy", "DE", "inactive", "low"),
        ("Atlas Spice Traders", "MA", "blocked", "high"),
        ("Iberia Olive Co.", "ES", "active", "medium"),
    ]
    for i, (name, iso, status, risk) in enumerate(samples):
        supplier, created = Supplier.objects.get_or_create(
            organisation=org,
            name=name,
            defaults={
                "email": f"contact{i + 1}@{name.lower().split()[0]}.example",
                "contact_name": f"Contact {i + 1}",
                "country": Country.objects.get(iso_code=iso),
                "status": status,
                "risk_level": risk,
            },
        )
        if not created:
            continue
        # One valid, one expiring soon, one expired: covers every status badge.
        Certificate.objects.create(
            supplier=supplier, certificate_type="globalgap", certificate_number=f"GG-{1000 + i}",
            issue_date=today - timedelta(days=200), expiry_date=today + timedelta(days=165),
        )
        if i % 2 == 0:
            Certificate.objects.create(
                supplier=supplier, certificate_type="iso_9001", certificate_number=f"ISO-{2000 + i}",
                issue_date=today - timedelta(days=340), expiry_date=today + timedelta(days=12),
            )
        if i % 3 == 0:
            Certificate.objects.create(
                supplier=supplier, certificate_type="organic_eu", certificate_number=f"ORG-{3000 + i}",
                issue_date=today - timedelta(days=400), expiry_date=today - timedelta(days=35),
            )
        Audit.objects.create(
            supplier=supplier, audit_date=today - timedelta(days=20 + i * 10),
            auditor="Jane Auditor", score=55 + i * 8, notes="Routine annual audit.",
        )


def reset_database(with_sample_data: bool = False):
    """Wipe everything and load the baseline again (reference data + users)."""
    call_command("flush", interactive=False, verbosity=0)
    call_command("loaddata", "reference_data", verbosity=0)
    seed_users()
    if with_sample_data:
        seed_sample_data()
