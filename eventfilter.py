"""Implements a bunch of handy event filters for reacting to events.

It's important to keep a copy of each event filter in a Python variable
so the garbage collector doesn't destroy it. They can be reused and
shared between multiple widgets.
"""

import logging
from typing import (
    Callable,
)

from PyQt5.QtCore import (  # type: ignore
    Qt,
    QObject,
    QEvent,
)

logger = logging.getLogger(__name__)


class EditDoneEventFilter(QObject):
    """Perform the passed function when a QLineEdit is done being edited.

    You can finish editing by either pressing Enter/Return, or by
    deselecting the widget.
    """

    def __init__(self, func_handle: Callable[[], None]):
        super().__init__()
        self.func_handle = func_handle

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Don't return True to mark these events as handled; let them pass.
        if event.type() == QEvent.FocusOut:  # type: ignore
            self.func_handle()
        elif (event.type() == QEvent.KeyPress  # type: ignore
              and event.key() in [Qt.Key_Return, Qt.Key_Enter]):  # type: ignore
            self.func_handle()
        return super().eventFilter(obj, event)


class ResizeEventFilter(QObject):
    """Perform the passed function when the associated widget is resized."""

    def __init__(self, func_handle: Callable[[], None]):
        super().__init__()
        self.func_handle = func_handle

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Don't return True to mark these events as handled; let them pass.
        if event.type() == QEvent.Resize:  # type: ignore
            self.func_handle()
        return super().eventFilter(obj, event)


class MouseWheelEventFilter(QObject):
    """Prevent mouse wheel events from reaching the target when out of focus."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Wheel and not obj.hasFocus():  # type: ignore
            return True
        return super().eventFilter(obj, event)


class ObserveEvents(QObject):
    """This event filter allows you to view all events received by a widget.

    For debugging only."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        logger.debug(f"{obj}, {event}")
        return super().eventFilter(obj, event)


MOUSE_WHEEL_EVENT_FILTER = MouseWheelEventFilter()
OBSERVE_EVENTS = ObserveEvents()
