"""Install Python dependencies declared by the LivingColor plugin."""

from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_IMPORT_ALIASES = {
    "stripe": "stripe",
}

_PIP_INSTALL_ATTEMPTED: set[str] = set()


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_pip_dependencies() -> list[str]:
    yaml_path = _plugin_root() / "plugin.yaml"
    if not yaml_path.is_file():
        return ["stripe"]
    try:
        import yaml
    except ImportError:
        return ["stripe"]

    try:
        payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.warning("Could not read plugin.yaml for pip dependencies", exc_info=True)
        return ["stripe"]

    deps = payload.get("pip_dependencies") or []
    if not isinstance(deps, list):
        return ["stripe"]
    normalized = [str(item).strip() for item in deps if str(item).strip()]
    return normalized or ["stripe"]


def _import_name_for_package(package: str) -> str:
    base = package.split("[", 1)[0].strip()
    return _IMPORT_ALIASES.get(base, base.replace("-", "_"))


def _package_importable(package: str) -> bool:
    import_name = _import_name_for_package(package)
    return importlib.util.find_spec(import_name) is not None


def ensure_pip_package(
    package: str,
    *,
    installer: Callable[[list[str]], None] | None = None,
) -> None:
    """Import *package*, installing it with pip/uv when missing."""
    if _package_importable(package):
        return
    if package in _PIP_INSTALL_ATTEMPTED:
        return
    _PIP_INSTALL_ATTEMPTED.add(package)

    if installer is not None:
        installer([package])
        if _package_importable(package):
            return
        raise RuntimeError(f"Required Python package {package!r} is not available")

    missing = [package]
    logger.info("Installing LivingColor plugin dependency: %s", package)
    uv_path = shutil.which("uv")
    if uv_path:
        cmd = [uv_path, "pip", "install", "--python", sys.executable, "--quiet", *missing]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--quiet", *missing]
    subprocess.run(cmd, check=False)
    if not _package_importable(package):
        raise RuntimeError(
            f"Required Python package {package!r} is not installed. "
            f"Run: {' '.join(cmd)}"
        )


def ensure_plugin_python_dependencies(
    *,
    installer: Callable[[list[str]], None] | None = None,
) -> None:
    """Ensure all pip dependencies from plugin.yaml are importable."""
    for package in _read_pip_dependencies():
        ensure_pip_package(package, installer=installer)
