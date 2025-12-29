from django.contrib.auth import get_user_model
from django.utils import timezone

import factory

from portfolio.models import (
    Account,
    AccountGroup,
    AccountType,
    AllocationStrategy,
    AssetClass,
    AssetClassCategory,
    Holding,
    Institution,
    Portfolio,
    Security,
    SecurityPrice,
    TargetAllocation,
)

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")


class PortfolioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Portfolio

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Portfolio {n}")


class InstitutionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Institution

    name = factory.Sequence(lambda n: f"Institution {n}")


class AccountGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AccountGroup

    name = factory.Sequence(lambda n: f"Group {n}")


class AccountTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AccountType

    code = factory.Sequence(lambda n: f"TYPE_{n}")
    label = factory.Sequence(lambda n: f"Type {n}")
    group = factory.SubFactory(AccountGroupFactory)


class AccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Account

    user = factory.SubFactory(UserFactory)
    portfolio = factory.SubFactory(PortfolioFactory, user=factory.SelfAttribute("..user"))
    name = factory.Sequence(lambda n: f"Account {n}")
    institution = factory.SubFactory(InstitutionFactory)
    account_type = factory.SubFactory(AccountTypeFactory)


class AssetClassCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AssetClassCategory

    code = factory.Sequence(lambda n: f"CAT_{n}")
    label = factory.Sequence(lambda n: f"Category {n}")


class AssetClassFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AssetClass

    name = factory.Sequence(lambda n: f"Asset Class {n}")
    category = factory.SubFactory(AssetClassCategoryFactory)


class SecurityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Security

    ticker = factory.Sequence(lambda n: f"TICK{n}")
    name = factory.Sequence(lambda n: f"Security {n}")
    asset_class = factory.SubFactory(AssetClassFactory)


class HoldingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Holding

    account = factory.SubFactory(AccountFactory)
    security = factory.SubFactory(SecurityFactory)
    shares = factory.Faker("pydecimal", left_digits=4, right_digits=4, positive=True)


class SecurityPriceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SecurityPrice

    security = factory.SubFactory(SecurityFactory)
    price = factory.Faker("pydecimal", left_digits=3, right_digits=2, positive=True)
    price_datetime = factory.LazyFunction(timezone.now)
    source = "factory"


class AllocationStrategyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AllocationStrategy

    user = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Strategy {n}")


class TargetAllocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TargetAllocation

    strategy = factory.SubFactory(AllocationStrategyFactory)
    asset_class = factory.SubFactory(AssetClassFactory)
    target_percent = factory.Faker(
        "pydecimal", left_digits=2, right_digits=2, min_value=0, max_value=100
    )
