from django.contrib import admin

from .models import (
    Account,
    AccountGroup,
    AccountType,
    AssetCategory,
    AssetClass,
    Holding,
    Institution,
    RebalancingRecommendation,
    Security,
    TargetAllocation,
)


class InstitutionAdmin(admin.ModelAdmin):
    search_fields = ('name',)

class AccountGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order')
    ordering = ('sort_order',)

class AccountTypeAdmin(admin.ModelAdmin):
    list_display = ('label', 'code', 'group', 'tax_treatment')
    list_filter = ('group', 'tax_treatment')
    ordering = ('group', 'label')

class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'account_type', 'get_group', 'institution')
    list_filter = ('account_type__group', 'institution')
    search_fields = ('name', 'user__username')
    # list_editable = ('group',) # Removed inline editing of group since it's derived

    @admin.display(description='Group', ordering='account_type__group')
    def get_group(self, obj: Account) -> str:
        return obj.account_type.group.name

admin.site.register(AssetCategory)
admin.site.register(AssetClass)
admin.site.register(Institution, InstitutionAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(AccountType, AccountTypeAdmin)
admin.site.register(AccountGroup, AccountGroupAdmin)
admin.site.register(Security)
admin.site.register(Holding)
admin.site.register(TargetAllocation)
admin.site.register(RebalancingRecommendation)
