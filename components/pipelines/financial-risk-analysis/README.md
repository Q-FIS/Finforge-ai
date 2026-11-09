# financial-risk-analysis Pipeline

An end-to-end FinForge AI pipeline for financial text normalization, domain-specific sentiment analysis, and multi-pillar risk evaluation.

---

## Architecture & DAG Topology

```
                  ┌──────────────────────┐
                  │     text_cleaner     │
                  └──────────┬───────────┘
                             │ cleaned_texts -> texts
                             ▼
                  ┌──────────────────────┐
                  │   sentiment_scorer   │
                  └──────────┬───────────┘
                             │ sentiment_results -> sentiment_results
                             │ sentiment_summary -> sentiment_summary
                             ▼
                  ┌──────────────────────┐
                  │     risk_tagger      │
                  └──────────────────────┘
```

### Components

1. **`text-cleaner`**:
   - Ingests financial news, earnings call transcripts, or regulatory disclosures.
   - Cleans HTML formatting, standardizes whitespace, strips boilerplate disclaimers, and normalizes punctuation while preserving financial terminology.
   - **Output Port**: `cleaned_texts` (`array` of `string`).

2. **`sentiment-scorer`**:
   - Implements Loughran-McDonald style domain-specific financial sentiment analysis.
   - Computes positive, negative, and uncertainty metrics per statement.
   - Generates compound sentiment scores (-1.0 to +1.0) and aggregate corpus metrics (`sentiment_summary`).
   - **Output Ports**: `sentiment_results` (`array`), `sentiment_summary` (`object`).

3. **`risk-tagger`**:
   - Classifies statements across 5 key financial risk pillars:
     - **Credit Risk**: defaults, downgrades, covenant breaches, maturity walls.
     - **Market Risk**: rate hikes, yield curve inversion, macroeconomic volatility, repricing.
     - **Liquidity Risk**: cash burn, refinancing constraints, withdrawal runs.
     - **Operational Risk**: supply chain disruption, outages, fraud.
     - **Regulatory Risk**: SEC subpoenas, enforcement actions, penalties, compliance.
   - Computes composite risk scores (0 to 100), severity levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and issues actionable mitigation recommendations.
   - **Output Ports**: `tagged_items` (`array`), `risk_assessment` (`object`).

---

## How to Inspect

Inspect nodes, connections, and topological ordering with the FinForge CLI:

```bash
finforge inspect pipeline.yaml
```

## How to Export Visual Diagrams

Export pipeline topology directly to visual formats:

```bash
# Print Mermaid flowchart to terminal
finforge export pipeline.yaml

# Export Mermaid diagram to file
finforge export pipeline.yaml --format mermaid -o topology.mmd

# Export Graphviz DOT format
finforge export pipeline.yaml --format dot -o topology.dot

# Export complete Markdown document with diagram & table
finforge export pipeline.yaml --format markdown -o topology.md
```

---

## How to Test Components

Run FinForge architectural validation and developer test suites across components:

```bash
finforge test components/text-cleaner
finforge test components/sentiment-scorer
finforge test components/risk-tagger
```

---

## How to Run

Execute the pipeline with default benchmark market dispatches:

```bash
python run_pipeline.py
```

Or pass custom financial statements directly via CLI:

```bash
python run_pipeline.py \
  --text "Operating cash flow expanded 25% following strong demand." \
  --text "Debt covenant breach and impending bond maturity threaten solvency."
```
