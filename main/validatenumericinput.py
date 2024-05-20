"""Helper functions for verifying numeric inputs from an unreliable user."""

#  Open Chrono-Morph Viewer, a project for visualizing volumetric time-series.
#  Copyright © 2024 Andre C. Faubert
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import math
from typing import Optional


def validate_int(value: str, min_: int, max_: Optional[int] = None,
                 default: Optional[int] = None) -> int:
    """Force value to be an int within min_ and max_."""

    try:
        ret = int(value)
    except ValueError:
        if default is None:
            ret = min_
        else:
            ret = default
    ret = max(min_, ret)
    if max_ is not None:
        ret = min(max_, ret)
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
