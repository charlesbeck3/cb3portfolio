"""
Custom Django system checks for portfolio application.

These checks run automatically with `manage.py check` and on server startup
to validate that the application is properly configured.

Django automatically discovers this file and registers all checks decorated
with @register() - no manual registration needed.
"""

from django.core.checks import Error, Warning, register

import structlog

logger = structlog.get_logger(__name__)


@register()
def check_asset_classes_exist(app_configs, **kwargs):
    """
    Verify that essential asset classes are defined.

    This check ensures that the system has been seeded with basic data
    required for the application to function properly.

    Returns:
        List of Warning objects if no asset classes exist.
    """
    try:
        from portfolio.models import AssetClass

        if not AssetClass.objects.exists():
            return [
                Warning(
                    "No asset classes defined in the database",
                    hint="Run: python manage.py seed_dev_data to create initial data",
                    id="portfolio.W001",
                )
            ]
    except Exception:
        # Database doesn't exist yet or tables not created
        # This is normal during initial setup, migrations, etc.
        return []

    return []


@register()
def check_account_types_exist(app_configs, **kwargs):
    """
    Verify that essential account types are defined.

    Returns:
        List of Warning objects if no account types exist.
    """
    try:
        from portfolio.models import AccountType

        if not AccountType.objects.exists():
            return [
                Warning(
                    "No account types defined in the database",
                    hint="Run: python manage.py seed_dev_data to create initial data",
                    id="portfolio.W002",
                )
            ]
    except Exception:
        # Database doesn't exist yet or tables not created
        return []

    return []


@register()
def check_cash_asset_class_exists(app_configs, **kwargs):
    """
    Verify that the special 'Cash' asset class exists.

    The Cash asset class is required for proper functioning of allocation
    calculations and is expected to have the exact name 'Cash'.

    Returns:
        List of Error objects if Cash asset class doesn't exist.
    """
    try:
        from portfolio.models import AssetClass

        if not AssetClass.objects.filter(name=AssetClass.CASH_NAME).exists():
            return [
                Error(
                    f"Required asset class '{AssetClass.CASH_NAME}' does not exist",
                    hint="Run: python manage.py seed_dev_data to create required system data",
                    id="portfolio.E001",
                )
            ]
    except Exception:
        # Database doesn't exist yet or tables not created
        return []

    return []
