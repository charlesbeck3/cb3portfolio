from typing import Any

from django.core.management.base import BaseCommand

from portfolio.services.seeder import SystemSeederService


class Command(BaseCommand):
    help = "Seeds the database with system reference data (Asset Classes, Account Types, etc.)"

    def handle(self, *args: Any, **options: Any) -> None:
        class CommandLogger:
            def __init__(self, command: BaseCommand) -> None:
                self.command = command

            def write(self, msg: str) -> None:
                self.command.stdout.write(msg)

            def success(self, msg: str) -> None:
                self.command.stdout.write(self.command.style.SUCCESS(msg))

        seeder = SystemSeederService(logger=CommandLogger(self))
        seeder.run()
