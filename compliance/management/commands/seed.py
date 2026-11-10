from django.core.management import call_command
from django.core.management.base import BaseCommand

from compliance.seed import DEFAULT_PASSWORD, BASELINE_USERS, seed_sample_data, seed_users


class Command(BaseCommand):
    help = "Load reference data and the baseline test users (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--sample-data", action="store_true", help="Also create sample suppliers to click around.")

    def handle(self, *args, **options):
        call_command("loaddata", "reference_data", verbosity=0)
        seed_users()
        if options["sample_data"]:
            seed_sample_data()
        self.stdout.write(self.style.SUCCESS("Seed complete. Test users (password: %s):" % DEFAULT_PASSWORD))
        for u in BASELINE_USERS:
            self.stdout.write(f"  {u['email']:<24} {u['role']:<7} {u['org']}")
