"""Implementation of PortfolioLoaderComponent."""

from __future__ import annotations

from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentLifecycleError,
)


class PortfolioLoaderComponent(BaseComponent):
    """Loads asset risk metrics and exposures for portfolio clustering."""

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._volatility_scale: float = 1.0

    def setup(self, config: dict[str, Any]) -> None:
        raw_scale = config.get("volatility_scale", 1.0)
        if not isinstance(raw_scale, (int, float)) or isinstance(raw_scale, bool):
            raise ComponentConfigurationError(
                f"Invalid 'volatility_scale': expected numeric, got {type(raw_scale).__name__}"
            )
        self._volatility_scale = float(raw_scale)
        self._is_configured = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._is_configured:
            raise ComponentLifecycleError("Call setup() before run().")

        assets = [
            {"symbol": "AAPL", "vol": 0.18 * self._volatility_scale, "dd": 0.12, "exposure": 25000.0},
            {"symbol": "MSFT", "vol": 0.15 * self._volatility_scale, "dd": 0.09, "exposure": 30000.0},
            {"symbol": "TSLA", "vol": 0.45 * self._volatility_scale, "dd": 0.38, "exposure": 45000.0},
            {"symbol": "BTC", "vol": 0.72 * self._volatility_scale, "dd": 0.65, "exposure": 50000.0},
            {"symbol": "ETH", "vol": 0.68 * self._volatility_scale, "dd": 0.58, "exposure": 40000.0},
        ]

        features = [[a["vol"], a["dd"]] for a in assets]
        symbols = [a["symbol"] for a in assets]
        max_exp = max(a["exposure"] for a in assets)

        return {
            "features": features,
            "max_exposure": max_exp,
            "asset_symbols": symbols,
        }

    def teardown(self) -> None:
        self._is_configured = False
