"""Tests for LivingColor plugin dependency bootstrap."""

from __future__ import annotations

import sys

import pytest

from lc_server.integrations import plugin_dependencies as module


def test_read_pip_dependencies_reads_plugin_yaml():
    deps = module._read_pip_dependencies()
    assert "stripe" in deps


def test_ensure_pip_package_skips_when_importable(monkeypatch):
    calls: list[list[str]] = []

    def fake_installer(packages: list[str]) -> None:
        calls.append(packages)

    monkeypatch.setattr(module, "_package_importable", lambda _package: True)
    module.ensure_pip_package("stripe", installer=fake_installer)
    assert calls == []


def test_ensure_pip_package_installs_when_missing(monkeypatch):
    calls: list[list[str]] = []
    state = {"importable": False}

    def fake_installer(packages: list[str]) -> None:
        calls.append(packages)
        state["importable"] = True

    monkeypatch.setattr(module, "_package_importable", lambda _package: state["importable"])
    module._PIP_INSTALL_ATTEMPTED.discard("stripe")
    module.ensure_pip_package("stripe", installer=fake_installer)
    assert calls == [["stripe"]]


def test_ensure_pip_package_raises_when_install_fails(monkeypatch):
    monkeypatch.setattr(module, "_package_importable", lambda _package: False)
    module._PIP_INSTALL_ATTEMPTED.discard("missing-package")

    with pytest.raises(RuntimeError, match="missing-package"):
        module.ensure_pip_package("missing-package", installer=lambda _packages: None)
