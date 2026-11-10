from django.core.management.base import BaseCommand

from compliance.seed import reset_database


class Command(BaseCommand):
    help = "Wipe all data and reload the baseline (reference data + test users)."

    def add_arguments(self, parser):
        parser.add_argument("--sample-data", action="store_true")

    def handle(self, *args, **options):
        reset_database(with_sample_data=options["sample_data"])
        self.stdout.write(self.style.SUCCESS("Database reset to baseline."))
