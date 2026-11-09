#!/usr/bin/env python3
"""Execution script for 'financial-risk-analysis' pipeline."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

pipeline_dir = Path(__file__).resolve().parent
repo_root = pipeline_dir.parents[2]
venv_python = repo_root / ".venv" / "bin" / "python"

# If current interpreter is missing finforge, auto re-exec with workspace virtualenv
if venv_python.exists() and sys.executable != str(venv_python):
    try:
        import finforge  # noqa: F401
    except ImportError:
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)

# Ensure finforge src is in sys.path
finforge_src = repo_root / "src"
if finforge_src.is_dir() and str(finforge_src) not in sys.path:
    sys.path.insert(0, str(finforge_src))

local_comps = pipeline_dir / "components"

# Add local components src directories to sys.path
for comp_path in local_comps.glob("*/src"):
    if comp_path.is_dir() and str(comp_path) not in sys.path:
        sys.path.insert(0, str(comp_path))

from finforge import ComponentRegistry, Pipeline

DEMO_PORTFOLIO_DISPATCHES = [
    (
        "Quarterly net profit surged 34% YoY with record operating cash flow and resilient enterprise cloud demand."
    ),
    (
        "Credit rating downgraded to B- amid severe liquidity constraints, bond covenants breach, and looming debt maturity wall."
    ),
    (
        "The firm received an SEC subpoena initiating a formal regulatory enforcement investigation into internal accounting controls."
    ),
    (
        "Central bank interest rate hikes and yield curve inversion continue to drive equity volatility and macroeconomic asset repricing."
    ),
    (
        "Severe supply chain disruptions and freight bottleneck outages risk delaying product shipments across key regional markets."
    ),
]


def run_demo(custom_texts: list[str] | None = None) -> int:
    """Execute the financial risk analysis pipeline."""
    print("=" * 76)
    print("          FINFORGE AI - FINANCIAL RISK ANALYSIS PIPELINE          ")
    print("=" * 76)

    # 1. Discover local components inside this pipeline
    registry = ComponentRegistry()
    search_paths = [local_comps]

    workspace_comps = pipeline_dir.parents[1] / "components"
    if workspace_comps.exists():
        search_paths.append(workspace_comps)

    registry.discover(search_paths=search_paths)
    print(f"\n[1] Component Registry: Discovered {len(registry)} components.")

    # 2. Load and validate pipeline definition
    yaml_path = pipeline_dir / "pipeline.yaml"
    pipeline = Pipeline.load(yaml_path, registry=registry)
    pipeline.validate()

    order = pipeline.execution_order()
    print(f"[2] Pipeline Loaded: '{pipeline.name}'")
    print(f"    Execution Order: {' -> '.join(order)}")

    # 3. Prepare inputs
    texts_to_analyze = custom_texts or DEMO_PORTFOLIO_DISPATCHES
    print(f"[3] Ingesting {len(texts_to_analyze)} financial dispatches for risk analysis...")

    # 4. Execute pipeline
    result = pipeline.run(
        inputs={"text_cleaner": {"texts": texts_to_analyze}},
        context={"environment": "production_risk_demo"},
    )

    print("\n" + "=" * 76)
    print(f" Execution Status: {result.status.value.upper()}  (Duration: {result.duration_ms:.2f}ms)")
    print("=" * 76)

    if not result.success:
        print("\nExecution Errors:")
        for err in result.execution_errors:
            print(f"  ✗ {err}")
        return 1

    # Print Node Timings
    print("\n--- Pipeline Node Telemetry ---")
    for node_id, n_res in result.node_results.items():
        print(f"  ✓ [{node_id}] status={n_res.status.value:<9} duration={n_res.duration_ms:.2f}ms")

    # Extract Outputs
    tagged_items = result.get_output("risk_tagger", "tagged_items") or []
    risk_assessment = result.get_output("risk_tagger", "risk_assessment") or {}
    sentiment_summary = result.get_output("sentiment_scorer", "sentiment_summary") or {}

    # Print Item Breakdown
    print("\n--- Per-Dispatch Risk & Sentiment Analysis ---")
    for idx, item in enumerate(tagged_items, 1):
        txt = item.get("text", "")
        cats = ", ".join(item.get("categories", []))
        score = item.get("risk_score", 0.0)
        sev = item.get("severity", "UNKNOWN")
        compound = item.get("sentiment_compound", 0.0)
        print(f"\nItem #{idx}: \"{txt}\"")
        print(f"  • Sentiment Polarity : {compound:+.2f}")
        print(f"  • Identified Risks   : {cats}")
        print(f"  • Risk Score / Tier  : {score:.1f}/100 [{sev}]")

    # Print Executive Summary
    print("\n" + "=" * 76)
    print("                     EXECUTIVE RISK ASSESSMENT REPORT                     ")
    print("=" * 76)
    comp_score = risk_assessment.get("composite_risk_score", 0.0)
    risk_level = risk_assessment.get("risk_level", "UNKNOWN")
    primary_driver = risk_assessment.get("primary_risk_driver", "N/A")
    market_sent = sentiment_summary.get("overall_sentiment", "NEUTRAL")

    print(f" Composite Risk Score : {comp_score:.1f} / 100")
    print(f" Overall Risk Level   : {risk_level}")
    print(f" Market Sentiment     : {market_sent}")
    print(f" Primary Risk Driver  : {primary_driver}")

    dist = risk_assessment.get("category_distribution", {})
    print("\n Risk Category Distribution:")
    for cat, count in dist.items():
        bar = "█" * (count * 3)
        print(f"  - {cat:<18}: {count:>2} {bar}")

    alerts = risk_assessment.get("critical_alerts", [])
    if alerts:
        print("\n ⚠ Critical Risk Alerts:")
        for alert in alerts:
            print(f"  - {alert}")

    recs = risk_assessment.get("recommended_actions", [])
    if recs:
        print("\n Recommended Mitigation Actions:")
        for rec in recs:
            print(f"  ✔ {rec}")

    print("=" * 76 + "\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Financial Risk Analysis Pipeline")
    parser.add_argument(
        "--text",
        "-t",
        action="append",
        dest="texts",
        help="Optional financial text item to analyze (can be passed multiple times)",
    )
    args = parser.parse_args()

    exit_code = run_demo(custom_texts=args.texts)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
