"""
Standard test data constants.

Using consistent values across tests makes test behavior predictable
and makes it easier to spot calculation errors.
"""
from decimal import Decimal

# Standard Holdings Values
STANDARD_SHARE_COUNT = Decimal("10")
STANDARD_SHARE_PRICE = Decimal("100.00")
STANDARD_HOLDING_VALUE = STANDARD_SHARE_COUNT * STANDARD_SHARE_PRICE  # $1,000

# Standard Allocation Percentages
PCT_100 = Decimal("100.00")
PCT_60 = Decimal("60.00")
PCT_40 = Decimal("40.00")
PCT_50 = Decimal("50.00")

# Standard User Credentials
TEST_USERNAME = "testuser"
TEST_PASSWORD = "password"

# Standard Names
DEFAULT_PORTFOLIO_NAME = "Test Portfolio"
DEFAULT_ACCOUNT_NAME = "Test Account"
