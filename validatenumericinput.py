"""Helper functions for verifying numeric inputs from an unreliable user."""

import math


def validate_int(value: str, min_: int, max_: int) -> int:
    """Force value to be an int within min_ and max_."""

    try:
        ret = int(value)
    except ValueError:
        ret = min_
    ret = max(min_, min(max_, ret))
    return ret


def validate_float(value: str, min_: float, max_: float) -> float:
    """Force value to be a real float within min_ and max_.

    Defaults to _min when a non-real value is passed, such as "NaN" or "-inf".
    """

    try:
        ret = float(value)
    except ValueError:
        ret = min_
    if math.isnan(ret) or math.isinf(ret):
        return min_
    ret = max(min_, min(max_, ret))
    return ret


def validate_float_any(value: str, default: float = 0) -> float:
    """Force value to be any real float, with a default upon failure."""

    try:
        ret = float(value)
    except ValueError:
        return default
    if math.isnan(ret) or math.isinf(ret):
        return default
    return ret


def nice_exp_format(x: str) -> str:
    """Make exponential string formats look nicer.

    Example: nice_format('5.234e+09') -> '5.234e9'
    """

    x = x.replace("e+0", "e")
    x = x.replace("e+", "e")
    x = x.replace("e-0", "e-")
    return x
