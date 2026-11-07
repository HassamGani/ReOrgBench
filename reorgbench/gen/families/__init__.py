"""More scenario families, one module each. A module registers its template on import."""

from importlib import import_module
from importlib.util import find_spec

for _name in ("sla_credit", "price_increase", "data_retention"):
    if find_spec(f"{__name__}.{_name}") is not None:
        import_module(f"{__name__}.{_name}")
