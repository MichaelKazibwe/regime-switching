import pandas as pd
from exceptions import (
    DataValidationError,
    
)

# ============================================================
# DATA VALIDATION
# ============================================================

class DataValidator:

    @staticmethod
    def validate_prices(
        df: pd.DataFrame
    ) -> bool:

        if df is None:
            raise DataValidationError(
                "Price frame is None"
            )

        if df.empty:
            raise DataValidationError(
                "Price frame empty"
            )

        if df.isnull().sum().sum() > 0:
            raise DataValidationError(
                "Missing prices detected"
            )

        if (df <= 0).sum().sum() > 0:
            raise DataValidationError(
                "Non-positive prices detected"
            )

        return True

    @staticmethod
    def validate_returns(
        returns: pd.DataFrame
    ) -> bool:

        if returns is None:
            raise DataValidationError(
                "Return frame is None"
            )

        if returns.empty:
            raise DataValidationError(
                "Return frame empty"
            )

        if returns.isnull().sum().sum() > 0:
            raise DataValidationError(
                "Missing returns detected"
            )

        return True