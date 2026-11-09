# text-cleaner

A FinForge AI component that normalizes and cleans financial news, transcripts, SEC filings, and market reports.

## Features
- Strips HTML/XML tags and entity encodings.
- Normalizes whitespace and punctuation.
- Optionally removes boilerplate forward-looking statement disclaimers.
- Preserves financial acronyms (e.g. SEC, EBITDA, Fed) or lowercases on demand.
- Supplies realistic benchmark financial text if input is not provided.

## Ports
- **Inputs**:
  - `texts` (`array` of `string`, optional): Raw financial text inputs.
- **Outputs**:
  - `cleaned_texts` (`array` of `string`): Normalized financial text items.
