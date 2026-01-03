from django.urls import path

from portfolio import views

app_name = "portfolio"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("holdings/", views.HoldingsView.as_view(), name="holdings"),
    path(
        "holdings/ticker/<str:ticker>/details/",
        views.TickerAccountDetailsView.as_view(),
        name="ticker_details",
    ),
    path("targets/", views.TargetAllocationView.as_view(), name="target_allocations"),
    path("account/<int:account_id>/", views.HoldingsView.as_view(), name="account_holdings"),
    path(
        "account/<int:account_id>/rebalance/",
        views.RebalancingView.as_view(),
        name="rebalancing",
    ),
    path(
        "account/<int:account_id>/rebalance/export/",
        views.RebalancingExportView.as_view(),
        name="rebalancing_export",
    ),
    path("strategies/new/", views.AllocationStrategyCreateView.as_view(), name="strategy_create"),
    path(
        "strategies/<int:pk>/edit/",
        views.AllocationStrategyUpdateView.as_view(),
        name="strategy_update",
    ),
]
