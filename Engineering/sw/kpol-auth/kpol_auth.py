"""Bootstrap shim enabling `PYTHONPATH=Engineering/sw/kpol-auth python3 -m kpol_auth`."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_real_package():
    pkg_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "kpol_auth",
        pkg_dir / "__init__.py",
        submodule_search_locations=[str(pkg_dir)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    _load_real_package()
    from kpol_auth.__main__ import main

    raise SystemExit(main())
else:
    _pkg = _load_real_package()
    globals().update({k: getattr(_pkg, k) for k in getattr(_pkg, "__all__", ())})
