from django.contrib import admin

from .models import (
    Account,
    AccountGroup,
    AssetCategory,
    AssetClass,
    Holding,
    RebalancingRecommendation,
    Security,
    TargetAllocation,
)


class AccountGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order')
    ordering = ('sort_order',)

class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'account_type', 'group', 'institution')
    list_filter = ('account_type', 'group', 'institution')
    search_fields = ('name', 'user__username')
    list_editable = ('group',)

admin.site.register(AssetCategory)
admin.site.register(AssetClass)
admin.site.register(Account, AccountAdmin)
admin.site.register(AccountGroup, AccountGroupAdmin)
admin.site.register(Security)
admin.site.register(Holding)
admin.site.register(TargetAllocation)
admin.site.register(RebalancingRecommendation)
