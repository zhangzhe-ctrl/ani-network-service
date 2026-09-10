#!/usr/bin/env python3
"""NET-05A adapter; see net05a-adapt.py for the count-checked runner changes."""
import importlib.util as _loader
from pathlib import Path as _Path
_spec=_loader.spec_from_file_location("net05a_adapt",_Path(__file__).with_name("net05a-adapt.py"))
_adapter=_loader.module_from_spec(_spec);_spec.loader.exec_module(_adapter)
exec(compile(_adapter.adapted('gates'),__file__,"exec"),globals())
