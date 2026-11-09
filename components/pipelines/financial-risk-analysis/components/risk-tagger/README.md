# risk-tagger

A FinForge AI component that categorizes financial risk pillars (Credit, Market, Liquidity, Operational, Regulatory), tags risk severity, and synthesizes an executive composite risk assessment report.

## Features
- Multi-dimensional taxonomy covering 5 major financial risk pillars.
- Integrates upstream sentiment signals and uncertainty indicators into composite risk scoring (0-100).
- Categorizes severity into CRITICAL, HIGH, MEDIUM, and LOW tiers.
- Emits actionable mitigation recommendations corresponding to detected risk pillars.

## Ports
- **Inputs**:
  - `sentiment_results` (`array`, required): Scored items from the sentiment scorer.
  - `sentiment_summary` (`object`, optional): Aggregated sentiment metrics.
- **Outputs**:
  - `tagged_items` (`array`): Enriched items with detected risk pillars and severity levels.
  - `risk_assessment` (`object`): Composite risk rating, distribution breakdown, and recommendations.
