"""The decision call (spec section 5): one typed call per utterance, deciding
whether it holds a claim or an open question worth checking, or repeats an
earlier candidate. Candidates are recorded, not shown, until step 4.
"""

from __future__ import annotations

from collections.abc import Mapping

from .session import Sessions


def install(sessions: Sessions, environ: Mapping[str, str]) -> None:
    """Plug the decision call into the sessions (`sessions.decider`)."""
