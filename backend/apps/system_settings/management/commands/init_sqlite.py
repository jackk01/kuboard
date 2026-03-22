from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Apply recommended SQLite pragmas for Kuboard single-node deployment."

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            self.stdout.write(self.style.WARNING("Current database is not SQLite, skipping pragmas."))
            return

        pragmas = {
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "foreign_keys": "ON",
            "busy_timeout": "5000",
            "wal_autocheckpoint": "1000",
        }

        with connection.cursor() as cursor:
            current_values: dict[str, str] = {}
            for key, value in pragmas.items():
                cursor.execute(f"PRAGMA {key}={value}")
                result = cursor.fetchone()
                if result:
                    current_values[key] = str(result[0])
                else:
                    cursor.execute(f"PRAGMA {key}")
                    fallback = cursor.fetchone()
                    current_values[key] = str(fallback[0]) if fallback else value

        for key, value in current_values.items():
            self.stdout.write(f"{key}={value}")

        self.stdout.write(self.style.SUCCESS("SQLite pragmas have been initialized."))
