from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seeds the database (System + Users)"

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Starting Database Seeding...")

        call_command("seed_system")
        call_command("seed_users")

        self.stdout.write(self.style.SUCCESS("--------------------------------------"))
        self.stdout.write(self.style.SUCCESS("FULL DATABASE SEED COMPLETE"))
        self.stdout.write(self.style.SUCCESS("--------------------------------------"))
