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
    list_display = ("name", "category", "expected_return")
    list_filter = ("category",)
    search_fields = ("name",)
    ordering = ("name",)


class SecurityAdmin(admin.ModelAdmin):
    list_display = ("ticker", "name", "asset_class", "get_asset_class_category")
    list_filter = ("asset_class__category", "asset_class")
    search_fields = ("ticker", "name")

    @admin.display(description="Category", ordering="asset_class__category")
    def get_asset_class_category(self, obj: Security) -> str:
        return obj.asset_class.category.label


class HoldingAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "security",
        "shares",
        "current_price",
        "get_market_value",
        "as_of_date",
    )
    list_filter = ("account", "security__asset_class")
    search_fields = ("security__ticker", "account__name")
    readonly_fields = ("as_of_date",)

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
admin.site.register(Holding, HoldingAdmin)
admin.site.register(TargetAllocation, TargetAllocationAdmin)
admin.site.register(RebalancingRecommendation)
