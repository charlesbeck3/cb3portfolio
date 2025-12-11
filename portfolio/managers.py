from typing import Any

from django.db import models


class AccountQuerySet(models.QuerySet):
    def for_user(self, user: Any) -> "AccountQuerySet":
        return self.filter(user=user)

    def with_details(self) -> "AccountQuerySet":
        return self.select_related("institution", "account_type__group").prefetch_related(
            "holdings__security__asset_class"
        )


class AccountManager(models.Manager):
    def get_queryset(self) -> AccountQuerySet:
        return AccountQuerySet(self.model, using=self._db)

    def for_user(self, user: Any) -> AccountQuerySet:
        return self.get_queryset().for_user(user)

    def get_summary_data(self, user: Any) -> AccountQuerySet:
        return self.for_user(user).with_details()


class HoldingQuerySet(models.QuerySet):
    def for_user(self, user: Any) -> "HoldingQuerySet":
        return self.filter(account__user=user)

    def with_security_details(self) -> "HoldingQuerySet":
        return self.select_related("security")

    def with_summary_details(self) -> "HoldingQuerySet":
        return self.select_related(
            "account",
            "account__account_type",
            "security",
            "security__asset_class",
            "security__asset_class__category",
            "security__asset_class__category__parent",
        )

    def for_category_view(self) -> "HoldingQuerySet":
        return self.select_related(
            "account", "account__account_type", "security", "security__asset_class"
        )


class HoldingManager(models.Manager):
    def get_queryset(self) -> HoldingQuerySet:
        return HoldingQuerySet(self.model, using=self._db)

    def for_user(self, user: Any) -> HoldingQuerySet:
        return self.get_queryset().for_user(user)

    def get_for_pricing(self, user: Any) -> HoldingQuerySet:
        return self.for_user(user).with_security_details()

    def get_for_summary(self, user: Any) -> HoldingQuerySet:
        return self.for_user(user).with_summary_details()

    def get_for_category_view(self, user: Any) -> HoldingQuerySet:
        return self.for_user(user).for_category_view()


class TargetAllocationQuerySet(models.QuerySet):
    def for_user(self, user: Any) -> "TargetAllocationQuerySet":
        return self.filter(user=user)

    def with_details(self) -> "TargetAllocationQuerySet":
        return self.select_related("asset_class", "account_type")


class TargetAllocationManager(models.Manager):
    def get_queryset(self) -> TargetAllocationQuerySet:
        return TargetAllocationQuerySet(self.model, using=self._db)

    def get_for_user(self, user: Any) -> TargetAllocationQuerySet:
        return self.get_queryset().for_user(user).with_details()
