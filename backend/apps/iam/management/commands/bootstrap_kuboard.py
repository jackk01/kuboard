from django.core.management.base import BaseCommand

from apps.iam.models import User


class Command(BaseCommand):
    help = "Create or update the default Kuboard administrator account."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@kuboard.local")
        parser.add_argument("--password", default="admin123456")
        parser.add_argument("--display-name", default="Kuboard Admin")

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            email=options["email"],
            defaults={
                "display_name": options["display_name"],
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.display_name = options["display_name"]
        user.is_staff = True
        user.is_superuser = True
        user.set_password(options["password"])
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} admin user {user.email}"))

