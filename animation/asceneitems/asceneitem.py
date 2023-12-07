import logging
from typing import (
    Any,
    Optional,
)

from sceneitems.sceneitem import load_bool

logger = logging.getLogger(__name__)


class ASceneItem:
    """The generic super-class for elements occupying space in the list
    widget as part of the Scene.
    """

    INITIAL_CHECK_STATE: Optional[bool] = None

    def __init__(self) -> None:
        # Is the checkbox checked?
        self.checked: bool = self.INITIAL_CHECK_STATE is not False

    def set_checked(self, checked: bool) -> None:
        """Check or uncheck the associated list item.

        If this item hasn't been added to the list, it is ignored.
        """

        logger.debug(f"set_checked({checked})")
        if self.INITIAL_CHECK_STATE is None:
            logger.debug(f"This type of item can't be checked.")
            return
        self.checked = checked

    def update_view(self, *_: Any) -> None:
        """Fill out visible information in the UI and VTK view port.

        This method might be called when the scroll area is not visible, in
        which case the UI will not be updated.

        This method can also be used as a VTK event callback, in which case
        the arguments are ignored.
        """

        if self.checked or self.INITIAL_CHECK_STATE is None:
            self._update_vtk()

    def _update_vtk(self) -> None:
        """Update information related to the VTK viewport."""

    def from_struct(self, struct: dict[str, Any]) -> list[str]:
        """Set values based on the data given in struct.

        Returns any errors that may have occurred when decoding.

        Does not update the view of this widget. That is left for the caller.
        """

        errors: list[str] = []
        if self.INITIAL_CHECK_STATE is not None:
            checked = load_bool("checked", struct, errors)
            if checked is not None:
                self.set_checked(checked)
        return errors
