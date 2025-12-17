from django.contrib import admin

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
    list_display = ("name", "user")
    list_filter = ("user",)
    search_fields = ("name", "user__username")
    inlines = (TargetAllocationInline,)


class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "allocation_strategy")
    list_filter = ("user",)
    search_fields = ("name", "user__username")


class AccountTypeStrategyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "account_type", "allocation_strategy")
    list_filter = ("user", "account_type")
    search_fields = ("user__username", "account_type__label", "allocation_strategy__name")


admin.site.register(AssetClassCategory)
admin.site.register(AssetClass)
admin.site.register(Institution, InstitutionAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(AccountType, AccountTypeAdmin)
admin.site.register(AccountGroup, AccountGroupAdmin)
admin.site.register(Portfolio, PortfolioAdmin)
admin.site.register(AllocationStrategy, AllocationStrategyAdmin)
admin.site.register(AccountTypeStrategyAssignment, AccountTypeStrategyAssignmentAdmin)
admin.site.register(Security)
admin.site.register(Holding)
admin.site.register(TargetAllocation)
admin.site.register(RebalancingRecommendation)
