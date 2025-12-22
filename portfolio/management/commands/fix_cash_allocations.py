from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from portfolio.models import AllocationStrategy, AssetClass, TargetAllocation


class Command(BaseCommand):
    help = "Add missing cash allocations to existing strategies"

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            cash_ac = AssetClass.objects.get(name="Cash")
        except AssetClass.DoesNotExist:
            self.stdout.write(self.style.ERROR("Cash asset class not found"))
            return

        fixed_count = 0

        for strategy in AllocationStrategy.objects.all():
            non_cash_allocations = strategy.target_allocations.exclude(asset_class=cash_ac)
            total = sum(ta.target_percent for ta in non_cash_allocations)

            # Check if total <= 100
            if total > Decimal("100.00"):
                self.stdout.write(
                    self.style.ERROR(
                        f"Strategy '{strategy.name}' (ID: {strategy.id}) total allocation {total}% > 100%. Skipping."
                    )
                )
                continue

            # Calculate expected cash
            cash_percent = Decimal("100.00") - total

            if cash_percent > 0:
                # Check existing cash allocation
                cash_ta = strategy.target_allocations.filter(asset_class=cash_ac).first()

                if not cash_ta or cash_ta.target_percent != cash_percent:
                    TargetAllocation.objects.update_or_create(
                        strategy=strategy,
                        asset_class=cash_ac,
                        defaults={"target_percent": cash_percent},
                    )
                    action = "Updated" if cash_ta else "Created"
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{action} cash allocation for '{strategy.name}': {cash_percent}% (Non-cash: {total}%)"
                        )
                    )
                    fixed_count += 1
            else:
                 # If cash should be 0, ensure it is 0 or deleted?
                 # save_allocations doesn't create 0% cash.
                 # So we should delete if exists?
                 # Or just update to 0?
                 # logic says: if cash_percent > 0: create.
                 # So if 0, we can delete existing cash allocation to be clean?
                 if strategy.target_allocations.filter(asset_class=cash_ac).exists():
                     strategy.target_allocations.filter(asset_class=cash_ac).delete()
                     self.stdout.write(
                         self.style.SUCCESS(f"Removed 0% cash allocation for '{strategy.name}'")
                     )
                     fixed_count += 1

        self.stdout.write(self.style.SUCCESS(f"Finished processing. Fixed {fixed_count} strategies."))
