"""
===============================================================
BASE COVARIANCE MODEL

Common functionality shared by every covariance estimator.

Every covariance model in the system should inherit from this
class.

===============================================================
"""

from abc import ABC, abstractmethod
from basecomponent import BaseObject

# ============================================================
# BASE COVARIANCE MODEL
# ============================================================

class BaseCovarianceModel(BaseObject,ABC):

    """
    Abstract base class for covariance models.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "estimate",

        "summary",

        "metadata"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        super().__init__()

        self.last_covariance = None

        self.last_summary = {}

    # ========================================================
    # ABSTRACT API
    # ========================================================

    @abstractmethod
    def estimate(
        self,
        *args,
        **kwargs
    ):
        """
        Estimate a covariance matrix.
        """
        raise NotImplementedError

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
    self
):

     return dict(
        self.last_summary
    )

    # ========================================================
    # METADATA
    # ========================================================

@property
def metadata(
    self
):

    metadata = super().metadata

    dimension = None

    if self.last_covariance is not None:

        dimension = self.last_covariance.shape[0]

    metadata.update(

        {

            "dimension":

                dimension

        }

    )

    return metadata