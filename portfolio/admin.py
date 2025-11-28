from django.contrib import admin

from .models import Account, AssetClass, Holding, Security, TargetAllocation

admin.site.register(AssetClass)
admin.site.register(Account)
admin.site.register(Security)
admin.site.register(Holding)
admin.site.register(TargetAllocation)
