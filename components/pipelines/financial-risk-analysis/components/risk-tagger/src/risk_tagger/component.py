"""Implementation of RiskTaggerComponent for financial risk evaluation."""

from __future__ import annotations

import re
from typing import Any

from finforge.component import BaseComponent
from finforge.exceptions import (
    ComponentConfigurationError,
    ComponentExecutionError,
    ComponentLifecycleError,
)

RISK_CATEGORIES: dict[str, list[str]] = {
    "Credit Risk": [
        "credit",
        "default",
        "downgrade",
        "covenant",
        "insolvency",
        "debt",
        "bond",
        "bonds",
        "maturity",
        "restructuring",
        "liquidation",
        "leverage",
    ],
    "Market Risk": [
        "market",
        "volatility",
        "volatile",
        "rate",
        "rates",
        "inflation",
        "inflationary",
        "repricing",
        "currency",
        "equity",
        "yield curve",
        "downturn",
        "macroeconomic",
    ],
    "Liquidity Risk": [
        "liquidity",
        "cash burn",
        "cash flow",
        "refinancing",
        "withdrawal",
        "redemption",
        "shortfall",
        "freeze",
    ],
    "Operational Risk": [
        "operational",
        "cyberattack",
        "supply chain",
        "failure",
        "outage",
        "disruption",
        "disruptions",
        "fraud",
        "irregularities",
    ],
    "Regulatory Risk": [
        "regulatory",
        "sec",
        "subpoena",
        "investigation",
        "investigations",
        "compliance",
        "enforcement",
        "sanctions",
        "penalty",
        "penalties",
        "lawsuit",
        "litigation",
        "antitrust",
    ],
}

RECOMMENDATIONS: dict[str, str] = {
    "Credit Risk": "Initiate credit facility review and evaluate debt covenant compliance margins.",
    "Market Risk": "Execute interest rate hedging and rebalance asset sensitivity exposure.",
    "Liquidity Risk": "Implement liquidity buffer stress tests and secure contingent credit lines.",
    "Operational Risk": "Audit critical vendor supply chains and enhance operational failover redundancy.",
    "Regulatory Risk": "Engage regulatory counsel and execute comprehensive internal control audit.",
}


class RiskTaggerComponent(BaseComponent):
    """Categorizes financial risk pillars and computes composite risk ratings."""

    def __init__(self) -> None:
        self._is_configured: bool = False
        self._risk_threshold: float = 50.0
        self._strict_mode: bool = False

    def setup(self, config: dict[str, Any]) -> None:
        """Configure risk tagging parameters.

        Args:
            config: Configuration dictionary matching component.yaml config schema.

        Raises:
            ComponentConfigurationError: If any configuration value is invalid.
        """
        raw_threshold = config.get("risk_threshold", 50.0)
        if not isinstance(raw_threshold, (int, float)):
            raise ComponentConfigurationError(
                f"Invalid 'risk_threshold': expected numeric, got {type(raw_threshold).__name__}"
            )
        self._risk_threshold = float(raw_threshold)

        raw_strict = config.get("strict_mode", False)
        if not isinstance(raw_strict, bool):
            raise ComponentConfigurationError(
                f"Invalid 'strict_mode': expected boolean, got {type(raw_strict).__name__}"
            )
        self._strict_mode = raw_strict

        self._is_configured = True

    def run(
        self,
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Tag items with risk categories and compute composite assessment.

        Args:
            inputs: Dictionary containing 'sentiment_results' and optional 'sentiment_summary'.
            context: Runtime execution context metadata.

        Returns:
            Dictionary containing 'tagged_items' and 'risk_assessment'.

        Raises:
            ComponentLifecycleError: If called before setup().
            ComponentExecutionError: If inputs are invalid or processing fails.
        """
        if not self._is_configured:
            raise ComponentLifecycleError(
                "Component must be configured via setup() before run()."
            )

        if "sentiment_results" not in inputs:
            raise ComponentExecutionError(
                "Missing required input port: 'sentiment_results'."
            )

        sentiment_results = inputs["sentiment_results"]
        if not isinstance(sentiment_results, list):
            raise ComponentExecutionError(
                f"Expected 'sentiment_results' to be a list, got {type(sentiment_results).__name__}."
            )

        tagged_items: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {cat: 0 for cat in RISK_CATEGORIES}
        total_risk_score = 0.0
        critical_alerts: list[str] = []

        for idx, item in enumerate(sentiment_results):
            if not isinstance(item, dict):
                raise ComponentExecutionError(
                    f"Item at index {idx} in 'sentiment_results' must be a dict, got {type(item).__name__}."
                )

            text = item.get("text", "")
            compound = float(item.get("compound_score", 0.0))
            unc_score = float(item.get("uncertainty_score", 0.0))
            text_lower = text.lower()

            matched_categories: list[str] = []
            keyword_hits = 0

            for cat, keywords in RISK_CATEGORIES.items():
                cat_hit = False
                for kw in keywords:
                    if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                        keyword_hits += 1
                        cat_hit = True
                if cat_hit:
                    matched_categories.append(cat)
                    category_counts[cat] += 1

            if not matched_categories:
                matched_categories = ["General Risk"]

            # Compute item risk score: 0 to 100
            score = 15.0 * len([c for c in matched_categories if c != "General Risk"])
            score += keyword_hits * 5.0

            if compound < 0:
                score += abs(compound) * 35.0
            else:
                score -= compound * 20.0

            score += unc_score * 25.0

            if self._strict_mode and keyword_hits > 0:
                score += 10.0

            clamped_score = max(0.0, min(100.0, score))
            total_risk_score += clamped_score

            if clamped_score >= 75.0:
                severity = "CRITICAL"
                critical_alerts.append(f"CRITICAL risk detected in: {text[:80]}...")
            elif clamped_score >= self._risk_threshold:
                severity = "HIGH"
            elif clamped_score >= 25.0:
                severity = "MEDIUM"
            else:
                severity = "LOW"

            tagged_items.append(
                {
                    "text": text,
                    "categories": matched_categories,
                    "risk_score": round(clamped_score, 2),
                    "severity": severity,
                    "sentiment_compound": compound,
                }
            )

        num_items = len(sentiment_results)
        mean_risk = total_risk_score / max(num_items, 1)

        # Determine composite risk level
        if mean_risk >= 70.0 or any(it["severity"] == "CRITICAL" for it in tagged_items):
            overall_level = "CRITICAL" if mean_risk >= 65.0 else "ELEVATED"
        elif mean_risk >= self._risk_threshold:
            overall_level = "ELEVATED"
        elif mean_risk >= 25.0:
            overall_level = "MODERATE"
        else:
            overall_level = "LOW"

        # Determine primary risk driver
        primary_driver = max(category_counts, key=lambda k: category_counts[k])
        if category_counts[primary_driver] == 0:
            primary_driver = "None (No significant risk factors detected)"

        # Collect actionable recommendations
        recommended_actions: list[str] = []
        for cat, count in category_counts.items():
            if count > 0 and cat in RECOMMENDATIONS:
                recommended_actions.append(f"[{cat}] {RECOMMENDATIONS[cat]}")

        if not recommended_actions:
            recommended_actions.append("Maintain routine market surveillance and risk monitoring.")

        assessment = {
            "composite_risk_score": round(float(mean_risk), 2),
            "risk_level": overall_level,
            "total_evaluated_items": num_items,
            "primary_risk_driver": primary_driver,
            "category_distribution": category_counts,
            "critical_alerts": critical_alerts,
            "recommended_actions": recommended_actions,
        }

        return {
            "tagged_items": tagged_items,
            "risk_assessment": assessment,
        }

    def teardown(self) -> None:
        """Clean up component state."""
        self._is_configured = False
