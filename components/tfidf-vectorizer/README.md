# tfidf-vectorizer

Scratch IDF and TF-IDF weighting component for FinForge AI — **RET-07** (issue #21).

- **Category**: `rag`
- **Version**: `0.1.0`
- **Entrypoint**: `tfidf_vectorizer.component:TfidfVectorizerComponent`
- **Runtime dependencies**: Python standard library + `finforge-ai` only

It fits a vocabulary and IDF weights on tokenised passages, then maps passages
and queries onto the same vocabulary dimensions as TF-IDF vectors.

```
tokenised passages ──fit──▶ vocabulary + df + IDF
tokenised passages ──transform──▶ document_vectors
tokenised queries  ──transform──▶ query_vectors (+ out-of-vocabulary terms)
```

---

## Concepts

| Symbol | Meaning |
|---|---|
| `N` | number of passages in the fitted collection |
| `tf(t, d)` | number of times term `t` occurs in passage `d` |
| `df(t)` | number of passages containing `t` at least once |
| `idf(t)` | how distinctive `t` is across the collection |

**IDF** gives more weight to rare terms. A term appearing in every passage
(`in`, `the`) does not help tell passages apart; a term in one passage
(`dividend`) does.

**TF-IDF** of term `t` in passage `d` is `tf(t, d) × idf(t)`. Each passage
becomes a vector with one dimension per vocabulary term, which is then
normalised so that long passages are not favoured just for being long.

### IDF conventions (`idf_convention`)

Textbook IDF and scikit-learn IDF are **not** the same formula. The convention
is therefore explicit configuration, never implicit.

| Value | Formula | Equivalent |
|---|---|---|
| `smooth` *(default)* | `ln((1 + N) / (1 + df)) + 1` | scikit-learn `TfidfVectorizer(smooth_idf=True)` |
| `unsmoothed` | `ln(N / df) + 1` | scikit-learn `TfidfVectorizer(smooth_idf=False)` |
| `textbook` | `ln(N / df)` | Manning, Raghavan & Schütze, *IIR* ch. 6 |

Smoothing acts as if one extra passage contained every term once, so no
division by zero can occur. The `+ 1` keeps terms that appear in every passage
at weight 1 rather than 0. Under `textbook`, such terms get weight 0.

### TF and normalisation

| Config | Values | Effect |
|---|---|---|
| `sublinear_tf` | `false` *(default)* / `true` | raw count, or `1 + ln(tf)` to damp repeated terms |
| `norm` | `l2` *(default)* / `l1` / `none` | divide each vector by its Euclidean length / sum of absolute values / leave as is |

---

## Ports

| Direction | Port | Type | Notes |
|---|---|---|---|
| in | `documents` | `array[array[string]]` | required; tokenised passages used to **fit** |
| in | `queries` | `array[array[string]]` | optional; **transformed only**, never change the IDF |
| out | `vocabulary` | `array[string]` | sorted; the column order of every vector |
| out | `idf` | `array[number]` | aligned with `vocabulary` |
| out | `document_frequency` | `array[integer]` | aligned with `vocabulary` |
| out | `document_vectors` | `array[array[number]]` | row `i` ↔ `documents[i]` |
| out | `query_vectors` | `array[array[number]]` | row `i` ↔ `queries[i]`; `[]` if no queries |
| out | `query_oov_terms` | `array[array[string]]` | terms of each query ignored as out-of-vocabulary |

Passage IDs and source metadata are kept aligned **by position**: whoever
supplies `documents[i]` keeps `passage_ids[i]`. This keeps the component free
of any particular metadata schema.

---

## Usage

### Through the FinForge pipeline (recommended)

```python
from finforge.manifest import load_manifest
from finforge.pipeline import Pipeline
from finforge.registry import ComponentRegistry
from tfidf_vectorizer import TfidfVectorizerComponent

registry = ComponentRegistry()
registry.register(
    TfidfVectorizerComponent,
    load_manifest("components/tfidf-vectorizer/component.yaml"),
)

pipeline = Pipeline("tfidf-demo", registry=registry)
pipeline.add("tfidf", "tfidf-vectorizer", config={"idf_convention": "smooth"})
result = pipeline.run(
    inputs={"tfidf": {"documents": [["revenue", "fy2025"], ["dividend", "fy2025"]],
                      "queries": [["revenue"]]}}
)
print(result.outputs["tfidf"]["query_vectors"])
```

The full runnable example is `examples/basic_usage.py`:

```bash
PYTHONPATH=components/tfidf-vectorizer/src \
    python components/tfidf-vectorizer/examples/basic_usage.py
```

### Directly (fit / transform)

```python
from tfidf_vectorizer import TfidfModel

model = TfidfModel(idf_convention="smooth").fit(passages)
query_vectors, oov = model.transform(queries)
```

---

## Tests

```bash
pip install -e ".[dev]"          # from the repository root: finforge-ai
pip install -e "components/tfidf-vectorizer[dev]"
pytest components/tfidf-vectorizer/tests
python -m finforge.cli.main test components/tfidf-vectorizer
```

The 39 tests cover:

- **Lifecycle**: `run()` before `setup()` raises; `teardown()` is idempotent.
- **Configuration**: unknown keys and invalid values raise `ComponentConfigurationError`.
- **Contract**: outputs pass `finforge.contracts.validate_outputs` against `component.yaml`.
- **Hand-computed values**: DF counts each passage once; every IDF convention; a full TF-IDF vector; sublinear TF; L1 and L2 norms.
- **Edge cases**: empty collection, empty vocabulary, untokenised text, non-string tokens, empty passage (zero vector), out-of-vocabulary queries, determinism.
- **scikit-learn parity**: 12 configurations (`smooth`/`unsmoothed` × sublinear on/off × `l2`/`l1`/`none`). Vocabulary order, IDF, passage vectors and query vectors all match `TfidfVectorizer` to an absolute tolerance of **1e-9**. These tests skip if scikit-learn is not installed.
- **Integration**: registers in `ComponentRegistry` and runs inside a `Pipeline`.

---

## Design decisions

1. **Tokens in, not raw text.** Tokenisation belongs to RET-02/RET-03. Taking
   token lists avoids hiding a second tokenizer here, and makes parity with
   scikit-learn exact (`TfidfVectorizer(analyzer=identity)`).
2. **Sorted vocabulary.** Deterministic column order that matches
   scikit-learn's `get_feature_names_out()`.
3. **Fit only on `documents`.** Queries are transformed with the fitted IDF, so
   searching never changes the index statistics.
4. **Out-of-vocabulary terms are reported**, not silently dropped.
5. **Pure Python with `math.fsum`.** Each number can be traced to a formula,
   and summation stays accurate enough for the 1e-9 parity requirement.
6. **Fresh model per `run()`.** The component holds no fitted state between
   runs, so pipeline re-runs cannot leak statistics from earlier data.

## Limitations

- **Dense output.** Vectors are dense lists of length `|vocabulary|`. That is
  fine for development corpora but uses `O(passages × vocabulary)` memory.
  The sparse CSR representation is RET-08.
- **No similarity or ranking.** Cosine scoring is RET-09 and top-k search is RET-10.
- **Refits every run.** A persistent fitted index across runs would need state
  handling that FinForge's component lifecycle does not currently define.
- **No `min_df` / `max_df` / vocabulary pruning yet.**

## Failure cases

- **Wrong tokenizer upstream.** If `₹1,45,000` is split into `₹1`, `45`, `000`,
  then `000` becomes a frequent, low-IDF term and the amount can no longer be
  matched as one figure. TF-IDF faithfully weights whatever tokens it is given;
  the fix belongs in RET-02.
- **Textbook IDF on a small corpus.** With `idf_convention: textbook`, a term in
  every passage (for example `fy2025` in a single-year report) gets weight 0. A
  query consisting only of such terms produces an all-zero vector and matches
  nothing.
- **Raw text instead of tokens.** Passing `"revenue rose"` or
  `["revenue rose"]` raises `ComponentExecutionError` rather than treating each
  character or whole sentence as a token.

---

## FinForge APIs used

| API | Source |
|---|---|
| `BaseComponent` (`setup` / `run` / `teardown`) | `src/finforge/component.py` |
| `ComponentConfigurationError`, `ComponentExecutionError`, `ComponentLifecycleError` | `src/finforge/exceptions.py` |
| Manifest schema (`ComponentManifest`, `PortDefinition` with nested `items`, `ConfigDefinition`) | `src/finforge/manifest/models.py` |
| `load_manifest` | `src/finforge/manifest/parser.py` |
| `validate_inputs`, `validate_outputs` | `src/finforge/contracts/validator.py` |
| `ComponentRegistry.register`, `ComponentRegistry.get` | `src/finforge/registry/registry.py` |
| `Pipeline.add`, `Pipeline.run` | `src/finforge/pipeline/builder.py` |
| `run_component_tests` (manifest, structure, contracts, lifecycle and developer-test stages) | `src/finforge/testing/runner.py` |

No FinForge core files were modified.

## Origin

Ported from the team's exploratory notebook `tfidf_from_scratch_corrected.ipynb`
(smoothed IDF, L2 normalisation, scikit-learn comparison). Changes made while
porting:

- added a fit/transform split
- added configurable IDF conventions
- added OOV reporting
- tightened the parity tolerance from `np.allclose` defaults to 1e-9
