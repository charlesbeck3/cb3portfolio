class PortfolioError(Exception):
    """Base exception for all portfolio related errors."""

    pass


class CalculationError(PortfolioError):
    """Raised when a calculation fails (e.g., division by zero, invalid data)."""

    pass


class PricingError(PortfolioError):
    """Raised when there is an issue with pricing data (e.g., missing price)."""

    pass


class AllocationError(PortfolioError):
    """Raised when allocation validation fails (e.g., sum != 100%)."""

    pass


class OptimizationError(PortfolioError):
    """Raised when optimization fails effectively."""

    pass
