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

import logging
from typing import Optional

import psutil

from main.eventfilter import EditDoneEventFilter
from main.timeline import Timeline
from main.validatenumericinput import (
    nice_exp_format,
    validate_float,
)
from ui.main_window import Ui_MainWindow

logger = logging.getLogger(__name__)

# One Gigabyte in bytes.
GB: int = 1 << 30


class CacheLimiter:
    """Manages the cache target UI element and sets the cache target for the timeline.

    It would be cool if this dynamically checked the system RAM usage to adjust
    the cache size.
    """

    def __init__(self, ui: Ui_MainWindow, timeline: Timeline) -> None:
        self.ui: Ui_MainWindow = ui
        self.timeline: Timeline = timeline
        self.edit_filter_limit: Optional[EditDoneEventFilter] = None

    def init_cache_limit(self) -> None:
        """Estimate how much memory is free to use for caching by looking at the
        system RAM utilization.
        """

        a = psutil.virtual_memory().available
        # Use up to 80% of the currently free memory and leave at least 1 gb available.
        self.set_cache_limit(max(0, min(a - GB, int(0.8 * a))))

    def set_cache_limit(self, cache_limit: int) -> None:
        """Update the UI and set this cache target in the timeline."""

        # Technically, this isn't a thread safe access, but it doesn't matter
        # due to the global interpreter lock.
        self.timeline.memory_target = cache_limit

        limit_gb: float = cache_limit / GB
        self.ui.edit_cache_limit.setText(nice_exp_format(f"{limit_gb:0.3g}"))
        logger.debug(f"Cache limit set to {cache_limit} bytes.")

    def bind_event_listeners(self) -> None:
        """Set UI input functions for the cache target edit box."""

        def update_limit() -> None:
            # Cache limit is specified in big Gigabytes.
            limit_gb = validate_float(self.ui.edit_cache_limit.text(), 0, 1e32)
            self.set_cache_limit(int(limit_gb * GB))

        self.edit_filter_limit = EditDoneEventFilter(update_limit)
        self.ui.edit_cache_limit.installEventFilter(self.edit_filter_limit)
