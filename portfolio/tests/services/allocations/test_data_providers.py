"""Tests for data providers."""

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
