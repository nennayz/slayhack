"""Compatibility re-export boundary for dashboard route helpers.

New grouped helper facades live under routes.helpers.*. Keep this module as the
historic import surface while route modules migrate gradually.
"""

from routes.helpers._legacy_core import *  # noqa: F401,F403
