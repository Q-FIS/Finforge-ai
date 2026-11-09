# sentiment-scorer

A FinForge AI component for financial domain sentiment scoring and polarity analysis.

## Features
- Implements Loughran-McDonald style domain-specific financial sentiment analysis.
- Computes positive, negative, and uncertainty metrics per financial statement.
- Produces normalized compound polarity scores (-1.0 to +1.0) and categorical labels (POSITIVE, NEUTRAL, NEGATIVE).
- Generates corpus-level aggregate financial sentiment summaries (BULLISH, BEARISH, NEUTRAL).

## Ports
- **Inputs**:
  - `texts` (`array` of `string`, required): Normalized financial statements.
- **Outputs**:
  - `sentiment_results` (`array`): Per-statement sentiment metrics and scores.
  - `sentiment_summary` (`object`): Aggregated market sentiment metrics.
