"""
===============================================================
BASE OBJECT

Institutional base class for every production object.

Provides

    • Versioning
    • Metadata
    • Summary
    • Serialization
    • Validation
    • Health Check
    • Representation

===============================================================
"""

import json
from abc import ABC

# ============================================================
# BASE OBJECT
# ============================================================

class BaseObject(ABC):

    """
    Base class for every production object.
    """

    API_VERSION = "1.0.0"

    PUBLIC_METHODS = (

        "summary",

        "metadata",

        "health_check",

        "validate",

        "to_dict",

        "save_json"

    )

    # ========================================================
    # CONSTRUCTOR
    # ========================================================

    def __init__(self):

        self._summary = {}

    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(
        self
    ):

        return dict(
            self._summary
        )

    # ========================================================
    # METADATA
    # ========================================================

    @property
    def metadata(
        self
    ):

        return {

            "class":

                self.__class__.__name__,

            "version":

                self.API_VERSION

        }

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate(
        self
    ):

        return True

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self
    ):

        self.validate()

        return True

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(
        self
    ):

        return dict(
            self.metadata
        )

    # ========================================================
    # SAVE
    # ========================================================

    def save_json(
        self,
        filename
    ):

        with open(

            filename,

            "w",

            encoding="utf-8"

        ) as f:

            json.dump(

                self.to_dict(),

                f,

                indent=4

            )

    # ========================================================
    # REPRESENTATION
    # ========================================================

    def __repr__(
        self
    ):

        return (

            f"{self.__class__.__name__}"

            f"(version={self.API_VERSION})"

        )

    def __str__(
        self
    ):

        return self.__repr__()