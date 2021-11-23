import sys

from schema import Schema, SchemaError


def inCloud() -> bool:
    """Returns True if we're in the cloud, False if not."""

    if sys.platform != "win32":
        return True
    return False


def schemaCheck(schema: Schema, dict_: dict) -> bool:
    """Returns True if the schema of dict_ matches that of schema."""

    try:
        schema.validate(dict_)
        return True
    except SchemaError:
        return False
