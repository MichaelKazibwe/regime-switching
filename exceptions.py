class TradingSystemError(Exception):
    """Base exception for the trading system."""
    pass


class MarketDataError(TradingSystemError):
    pass


class DataValidationError(TradingSystemError):
    pass


class OptimizationError(TradingSystemError):
    pass


class RiskModelError(TradingSystemError):
    pass


class ExecutionError(TradingSystemError):
    pass


class DatabaseError(TradingSystemError):
    pass


class BrokerError(TradingSystemError):
    pass

class RiskLimitBreach(TradingSystemError):
    """Raised when portfolio risk limits are exceeded."""
    pass