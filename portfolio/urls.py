from django.urls import path

from . import views

app_name = 'portfolio'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('holdings/', views.HoldingsView.as_view(), name='holdings'),
    path('targets/', views.TargetAllocationView.as_view(), name='target_allocations'),
    path('account/<int:account_id>/', views.HoldingsView.as_view(), name='account_holdings'),
]
