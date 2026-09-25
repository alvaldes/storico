"""The version Storico publishes about itself.

One fact, one reader: the FastAPI metadata that `/docs` renders and the three health
routes all answer this, and the literal ``"0.1.0"`` each of them used to carry had been
wrong since the package reached ``0.3.0``. It was fixed in the health routes first, which
left ``:8000/docs`` announcing 0.1.0 while ``/api/v1/health`` announced 0.5.1 in the same
process, on the same request. The value is therefore read in exactly one place.
"""

import importlib.metadata
import logging

logger = logging.getLogger(__name__)

_DISTRIBUTION = "storico-backend"


def package_version() -> str:
    """The installed distribution's version, or ``"unknown"``.

    Read rather than hardcoded, and allowed to fail: the lookup goes to installed metadata,
    and a request that renders metadata is worse than one that admits it does not know. The
    exception goes to the log, where an operator can read it, never to the response.
    """
    try:
        return importlib.metadata.version(_DISTRIBUTION)
    except Exception:
        logger.warning("Could not read the installed package version", exc_info=True)
        return "unknown"
