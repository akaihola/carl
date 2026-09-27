"""Location (spec section 12): the phone's fixes become a place name on the
server, through Nominatim, and each stage gets the place context it may have.
Coordinates never go to any model.
"""

from __future__ import annotations

from collections.abc import Mapping

from .session import Sessions


def install(sessions: Sessions, environ: Mapping[str, str]) -> None:
    """Plug location into the sessions (`sessions.locator`)."""
