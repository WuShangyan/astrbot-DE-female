"""Vivian Vale AstrBot plugin package init.

AstrBot's plugin loader does not add the plugin directory to ``sys.path``,
so absolute ``from epigraphs import ...`` (used in banners.py) fails with
``ModuleNotFoundError``. Add the plugin directory to sys.path on import
so both relative ``from .epigraphs import ...`` and absolute
``import epigraphs`` resolve correctly.
"""

from __future__ import annotations

import os
import sys

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)