"""Unit tests for PortfolioLoaderComponent."""

from __future__ import annotations

import pytest

from finforge.exceptions import ComponentConfigurationError, ComponentLifecycleError
from portfolio_loader.component import PortfolioLoaderComponent


def test_portfolio_loader_lifecycle() -> None:
    comp = PortfolioLoaderComponent()
    with pytest.raises(ComponentLifecycleError):
        comp.run({}, {})

    comp.setup({"volatility_scale": 1.5})
    res = comp.run({}, {})

    assert "features" in res
    assert "max_exposure" in res
    assert "asset_symbols" in res
    assert len(res["features"]) == 5
    assert len(res["asset_symbols"]) == 5
    assert res["max_exposure"] == 50000.0

    comp.teardown()
    assert not comp._is_configured


def test_invalid_config() -> None:
    comp = PortfolioLoaderComponent()
    with pytest.raises(ComponentConfigurationError):
        comp.setup({"volatility_scale": "invalid"})
