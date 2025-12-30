from django.contrib import admin
from django.db.models import Sum

from .models import (
    Account,
    AccountGroup,
    AccountType,
    AccountTypeStrategyAssignment,
    AllocationStrategy,
    AssetClass,
    AssetClassCategory,
    Holding,
    Institution,
    Portfolio,
    RebalancingRecommendation,
    Security,
    SecurityPrice,
    TargetAllocation,
)


class InstitutionAdmin(admin.ModelAdmin):
    search_fields = ("name",)


class AccountGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    ordering = ("sort_order",)


class AccountTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "group", "tax_treatment")
    list_filter = ("group", "tax_treatment")
    ordering = ("group", "label")


class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "portfolio",
        "account_type",
        "get_group",
        "institution",
        "allocation_strategy",
    )
    list_filter = ("portfolio", "account_type__group", "institution")
    search_fields = ("name", "user__username")
    # list_editable = ('group',) # Removed inline editing of group since it's derived

    @admin.display(description="Group", ordering="account_type__group")
    def get_group(self, obj: Account) -> str:
        return obj.account_type.group.name


class TargetAllocationInline(admin.TabularInline):
    model = TargetAllocation
    extra = 0


class AllocationStrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "get_total_allocation", "is_active", "modified_date")
    list_filter = ("user", "is_active")
    search_fields = ("name", "user__username")
    inlines = (TargetAllocationInline,)

    @admin.display(description="Total Allocation %")
    def get_total_allocation(self, obj: AllocationStrategy) -> str:
        total = obj.target_allocations.aggregate(Sum("target_percent"))["target_percent__sum"]
        if total is None:
            return "0.00%"
        return f"{total}%"


class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "allocation_strategy")
    list_filter = ("user",)
    search_fields = ("name", "user__username")


class AccountTypeStrategyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "account_type", "allocation_strategy")
    list_filter = ("user", "account_type")
    search_fields = ("user__username", "account_type__label", "allocation_strategy__name")


class AssetClassAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "expected_return", "get_primary_ticker")
    list_filter = ("category",)
    search_fields = ("name",)
    ordering = ("name",)
    autocomplete_fields = ["primary_security"]

    fieldsets = (
        ("Basic Information", {"fields": ("name", "category", "expected_return")}),
        (
            "Primary Security",
            {"fields": ("primary_security",)},
        ),
    )

    @admin.display(description="Primary", ordering="primary_security__ticker")
    def get_primary_ticker(self, obj: AssetClass) -> str:
        if obj.primary_security:
            return obj.primary_security.ticker
        return "—"


class SecurityAdmin(admin.ModelAdmin):
    list_display = (
        "ticker",
        "name",
        "asset_class",
        "get_asset_class_category",
        "is_primary_display",
    )
    list_filter = ("asset_class__category", "asset_class")
    search_fields = ("ticker", "name")

    @admin.display(description="Category", ordering="asset_class__category")
    def get_asset_class_category(self, obj: Security) -> str:
        return obj.asset_class.category.label

    @admin.display(description="Primary", boolean=True)
    def is_primary_display(self, obj: Security) -> bool:
        return obj.is_primary_for_asset_class


class SecurityPriceAdmin(admin.ModelAdmin):
    """Admin for SecurityPrice model."""

    list_display = ["security", "price", "price_datetime", "source", "fetched_at"]
    list_filter = ["source", "price_datetime"]
    search_fields = ["security__ticker", "security__name"]
    date_hierarchy = "price_datetime"
    readonly_fields = ["fetched_at"]

    ordering = ["-price_datetime", "security__ticker"]

    fieldsets = (
        ("Price Information", {"fields": ("security", "price", "price_datetime")}),
        ("Metadata", {"fields": ("source", "fetched_at"), "classes": ("collapse",)}),
    )


class HoldingAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "security",
        "shares",
        "get_latest_price",
        "get_market_value",
        "as_of_date",
    )
    list_filter = ("account", "security__asset_class")
    search_fields = ("security__ticker", "account__name")
    readonly_fields = ("as_of_date",)

    @admin.display(description="Latest Price")
    def get_latest_price(self, obj: Holding) -> str:
        """Display latest price from SecurityPrice table."""
        price = obj.latest_price
        return f"${price:,.2f}" if price is not None else "N/A"

    @admin.display(description="Market Value")
    def get_market_value(self, obj: Holding) -> str:
        return f"${obj.market_value:,.2f}"


class TargetAllocationAdmin(admin.ModelAdmin):
    list_display = ("strategy", "asset_class", "target_percent")
    list_filter = ("strategy", "asset_class")
    search_fields = ("strategy__name", "asset_class__name")


admin.site.register(AssetClassCategory)
admin.site.register(AssetClass, AssetClassAdmin)
admin.site.register(Institution, InstitutionAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(AccountType, AccountTypeAdmin)
admin.site.register(AccountGroup, AccountGroupAdmin)
admin.site.register(Portfolio, PortfolioAdmin)
admin.site.register(AllocationStrategy, AllocationStrategyAdmin)
admin.site.register(AccountTypeStrategyAssignment, AccountTypeStrategyAssignmentAdmin)
admin.site.register(Security, SecurityAdmin)
admin.site.register(SecurityPrice, SecurityPriceAdmin)
admin.site.register(Holding, HoldingAdmin)
admin.site.register(TargetAllocation, TargetAllocationAdmin)
admin.site.register(RebalancingRecommendation)
