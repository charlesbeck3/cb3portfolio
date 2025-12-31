"""Tests for data providers."""

import pandas as pd
import pytest

from portfolio.services.allocations.data_providers import DjangoDataProvider


@pytest.mark.services
@pytest.mark.django_db
class TestDjangoDataProvider:
    """Test DjangoDataProvider."""

    @pytest.fixture
    def provider(self):
        """Create data provider instance."""
        return DjangoDataProvider()

    def test_get_holdings_df_structure(self, provider, test_user, simple_holdings):
        """Verify holdings DataFrame has correct structure."""
        df = provider.get_holdings_df(test_user)

        expected_cols = [
            "account_id",
            "account_name",
            "account_type_code",
            "asset_class",
            "asset_class_id",
            "category_code",
            "ticker",
            "shares",
            "price",
            "value",
        ]
        assert list(df.columns) == expected_cols
        assert len(df) > 0

    def test_get_holdings_df_empty(self, provider, test_user):
        """Verify empty DataFrame for user with no holdings."""
        df = provider.get_holdings_df(test_user)

        assert df.empty

    def test_get_asset_classes_df_structure(self, provider, test_user, base_system_data):
        """Verify asset classes DataFrame has correct structure."""
        df = provider.get_asset_classes_df(test_user)

        expected_cols = [
            "asset_class_id",
            "asset_class_name",
            "group_code",
            "group_label",
            "group_sort_order",
            "category_code",
            "category_label",
            "category_sort_order",
            "is_cash",
            "row_type",
        ]
        assert list(df.columns) == expected_cols
        assert len(df) > 0
        assert "is_cash" in df.columns

    def test_get_accounts_metadata_structure(self, provider, test_user, simple_holdings):
        """Verify accounts metadata has correct structure."""
        accounts_list, accounts_by_type = provider.get_accounts_metadata(test_user)

        assert isinstance(accounts_list, list)
        assert isinstance(accounts_by_type, dict)
        assert len(accounts_list) > 0

        # Check account structure
        account = accounts_by_type[list(accounts_by_type.keys())[0]][0]
        assert "id" in account
        assert "name" in account
        assert "type_code" in account
        assert "type_label" in account
        assert "institution" in account

    def test_get_targets_map_structure(self, provider, test_user, simple_holdings):
        """Verify targets map has correct structure."""
        targets = provider.get_targets_map(test_user)

        assert isinstance(targets, dict)
        # May be empty if no strategies assigned
        if targets:
            account_id = list(targets.keys())[0]
            allocations = targets[account_id]
            assert isinstance(allocations, dict)
            # Check that values are Decimal
            if allocations:
                asset_class = list(allocations.keys())[0]
                from decimal import Decimal

                assert isinstance(allocations[asset_class], Decimal)

    def test_get_holdings_df_detailed(self, provider, test_user, simple_holdings):
        """Verify detailed holdings DataFrame structure."""
        df = provider.get_holdings_df_detailed(test_user)

        assert "Ticker" in df.columns
        assert "Account_Name" in df.columns
        assert "Value" in df.columns
        assert len(df) > 0

    def test_get_holdings_df_detailed_with_account_id(
        self, provider, test_user, simple_holdings, roth_account
    ):
        """Verify detailed holdings filtering by account ID."""
        df = provider.get_holdings_df_detailed(test_user, account_id=roth_account.id)
        assert len(df) > 0
        assert (df["Account_ID"] == roth_account.id).all()

    def test_get_zero_holdings_for_targets(self, provider, test_user, base_system_data):
        """Verify zero holdings creation for missing targets."""
        from decimal import Decimal

        targets_map = {1: {"US Equities": Decimal("50.0")}}

        # Create an account but no holdings
        from portfolio.models import Account, AccountType, Institution, Portfolio

        portfolio = Portfolio.objects.create(user=test_user, name="Test Portfolio")
        account_type = AccountType.objects.first()
        institution = Institution.objects.first() or Institution.objects.create(name="Test Inst")
        _account = Account.objects.create(
            id=1,
            user=test_user,
            portfolio=portfolio,
            name="Test Account",
            account_type=account_type,
            institution=institution,
        )

        # Ensure US Equities has a primary security
        from portfolio.models import AssetClass, Security

        us_equities = AssetClass.objects.get(name="US Equities")
        vti, _ = Security.objects.get_or_create(
            ticker="VTI",
            defaults={"name": "Vanguard Total Stock Market", "asset_class": us_equities},
        )
        us_equities.primary_security = vti
        us_equities.save()

        df_zero = provider.get_zero_holdings_for_targets(pd.DataFrame(), targets_map, account_id=1)

        assert not df_zero.empty
        assert len(df_zero) == 1
        assert df_zero.iloc[0]["Asset_Class"] == "US Equities"
        assert df_zero.iloc[0]["Value"] == 0.0

    def test_get_effective_targets_for_portfolio(self, provider, test_user, simple_holdings):
        """Verify portfolio-level effective targets calculation."""
        result = provider.get_effective_targets_for_portfolio(test_user)
        assert isinstance(result, dict)
        assert 0 in result

    def test_get_policy_targets_for_portfolio(self, provider, test_user, test_portfolio):
        """Verify portfolio-level policy targets."""
        result = provider.get_policy_targets_for_portfolio(test_user)
        assert isinstance(result, dict)
        assert 0 in result
