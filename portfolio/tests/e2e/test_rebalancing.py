"""E2E tests for rebalancing workflow."""

from decimal import Decimal

from django.utils import timezone

import pytest
from playwright.sync_api import Page, expect

from portfolio.models import (
    AllocationStrategy,
    Holding,
    Security,
    SecurityPrice,
    TargetAllocation,
)


@pytest.mark.e2e
@pytest.mark.django_db
class TestRebalancingE2E:
    """E2E tests for rebalancing."""

    @pytest.fixture(autouse=True)
    def setup_data(self, test_portfolio, roth_account):
        """Setup standard test data."""
        system = test_portfolio["system"]
        user = test_portfolio["user"]

        # Create holdings in Roth IRA
        # $6000 VTI (60%)
        Holding.objects.create(
            account=roth_account,
            security=system.vti,
            shares=Decimal("30"),  # 30 * $200 = $6000
        )
        SecurityPrice.objects.create(
            security=system.vti,
            price=Decimal("200"),
            price_datetime=timezone.now(),
            source="test",
        )

        # $4000 BND (40%)
        # Need to ensure BND exists and MATCHES the target asset class
        # BND from seed data might be in "US Fixed Income", but here we target "Treasuries Short"
        bnd, _ = Security.objects.get_or_create(
            ticker="BND",
            defaults={
                "name": "Vanguard Total Bond Market ETF",
                "asset_class": system.asset_class_treasuries_short,
            },
        )
        # Force update asset class to match target (in case it already existed)
        bnd.asset_class = system.asset_class_treasuries_short
        bnd.is_primary = True
        bnd.save()

        Holding.objects.create(
            account=roth_account,
            security=bnd,
            shares=Decimal("50"),  # 50 * $80 = $4000
        )
        SecurityPrice.objects.create(
            security=bnd,
            price=Decimal("80"),
            price_datetime=timezone.now(),
            source="test",
        )

        # Create Strategy: 50/50 split (Needs rebalancing)
        strategy = AllocationStrategy.objects.create(
            user=user,
            name="50/50 Strategy",
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_us_equities,
            target_percent=Decimal("50.00"),
        )
        TargetAllocation.objects.create(
            strategy=strategy,
            asset_class=system.asset_class_treasuries_short,
            target_percent=Decimal("50.00"),
        )

        roth_account.allocation_strategy = strategy
        roth_account.save()

        return {
            "account": roth_account,
            "system": system,
        }

    def test_rebalancing_workflow(self, authenticated_page: Page, live_server, setup_data):
        """Test complete rebalancing workflow from account detail to plan display."""
        account = setup_data["account"]

        # Navigate to account detail page
        authenticated_page.goto(f"{live_server.url}/account/{account.id}/")

        # Find Rebalance button
        # Use role and name to handle potential whitespace
        rebalance_link = authenticated_page.get_by_role("link", name="Rebalance")

        # It might be inside a dropdown or directly visible depending on UI implementation
        # Assuming it's a visible link based on standard pattern
        if not rebalance_link.is_visible():
            # Try finding it as a link within the action menu if needed
            # For now assuming direct link as per standard button usage
            pass

        # Click Rebalance
        rebalance_link.click()

        # Verify Rebalancing Plan page
        expect(authenticated_page.get_by_role("heading", name="Rebalancing Plan")).to_be_visible()

        # Verify Pro Forma Holdings Analysis table exists
        expect(authenticated_page.get_by_text("Pro Forma Holdings Analysis")).to_be_visible()

        # Verify table headers (Pro Forma, Target, Variance)
        expect(authenticated_page.get_by_text("Pro Forma", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("Target", exact=True).first).to_be_visible()
        expect(authenticated_page.get_by_text("Variance", exact=True).first).to_be_visible()

        # Verify securities are listed in pro forma table
        proforma_table = authenticated_page.get_by_test_id("proforma-table")
        expect(proforma_table).to_be_visible()

        # Verify columns exist
        expect(proforma_table.get_by_text("Ticker")).to_be_visible()
        expect(proforma_table.get_by_text("Security")).to_be_visible()
        expect(proforma_table.get_by_text("Asset Class")).to_be_visible()

        # Verify securities present
        expect(proforma_table.get_by_text("VTI", exact=True)).to_be_visible()
        expect(proforma_table.get_by_text("BND", exact=True)).to_be_visible()

        # Verify grand total row exists
        expect(authenticated_page.get_by_test_id("proforma-grand-total")).to_be_visible()

        # Verify drift analysis
        drift_table = authenticated_page.get_by_test_id("drift-table")
        expect(drift_table).to_be_visible()

        # Verify orders table
        orders_table = authenticated_page.get_by_test_id("orders-table")
        expect(orders_table).to_be_visible()

        # Verify order content (Should sell VTI, Buy BND)
        orders_text = orders_table.inner_text()
        assert "VTI" in orders_text
        assert "SELL" in orders_text
        assert "BND" in orders_text
        assert "BUY" in orders_text
