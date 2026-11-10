# FinForge AI: Current Issues, Technical Debt & Architectural Limitations

**Document Version**: 1.0.0  
**Date**: November 2026  
**Repository**: `financial-rag-ml-team` (`finforge`)  
**Status**: Comprehensive Technical Audit & Issue Tracker  

---

## 1. Executive Summary

While **FinForge AI** has a functioning foundation—including a passing test suite (364 tests), complete Pydantic v2 declarative manifest validation, DAG cycle detection, and CLI tooling—an in-depth diagnostic audit reveals several active issues, technical debt items, and architectural limitations that need to be addressed before a public beta or production release.

These issues are classified into five major categories:
1. **Developer Tooling & Linting Violations** (Ruff formatting, Mypy namespace collisions)
2. **CLI Runtime Warnings & Test Fragility** (`runpy` module warnings, console table truncation)
3. **Repository Cleanliness & Stray Artifacts** (Ad-hoc test components left in workspace)
4. **Runtime & Execution Engine Limitations** (Sequential-only DAG execution, lack of streaming)
5. **Security & Sandboxing Boundaries** (Arbitrary Python code execution during dynamic imports)

---

## 2. Code Quality, Linting & Type Checking Issues

### 2.1 Ruff Linter Violations (76 Errors across Components and Pipelines)
- **Status**: 🔴 Active
- **Details**: Running `ruff check .` reports **76 linting errors** across components, generated templates, and pipeline scripts.
- **Key Violations**:
  - `E501 (Line too long)`: Multiple lines in `components/examples/custom_kmeans/src/my_kmeans/component.py` and `pipelines/portfolio-risk-clustering/components/portfolio-loader/src/portfolio_loader/component.py` exceed the 88-character limit.
  - `I001 (Import block un-sorted)`: Unsorted imports across generated tests in `components/hello/tests/test_component.py`, `components/bhavik/tests/test_component.py`, and `components/text-cleaner/tests/test_component.py`.
  - `B905 (zip() without strict=)`: `_dist_sq()` in `custom_kmeans` uses `zip(p1, p2)` without explicit `strict=False` or `strict=True`, causing potential silent truncation if vector lengths differ.
  - `E402 (Module level import not at top of file)`: In `pipelines/portfolio-risk-clustering/run_pipeline.py`, `sys.path.insert` occurs before `from finforge import Pipeline`, triggering an E402 violation.
- **Remediation**: Run `ruff check --fix .` and `ruff format .`, adjust template generators in `src/finforge/sdk/generator.py` so newly scaffolded components conform to PEP 8 / Ruff defaults automatically.

---

### 2.2 Mypy Duplicate Module Collision on Multi-Component Paths
- **Status**: 🟡 Active
- **Details**: Running `mypy components/ pipelines/` directly fails with:
  ```text
  components/examples/custom_kmeans/tests/test_component.py: error: Duplicate module named "test_component" (also at "components/bhavik/tests/test_component.py")
  ```
- **Root Cause**: Because every component created by `finforge create` follows the same folder structure (`tests/test_component.py`) without unique top-level package roots or `__init__.py` files in tests, Mypy interprets multiple identical module paths as collisions unless `--explicit-package-bases` is specified.
- **Remediation**: Configure `[tool.mypy]` in `pyproject.toml` with `explicit_package_bases = true` or namespace test files per component (e.g., `test_<component_name>.py`).

---

## 3. CLI & Runtime Warnings

### 3.1 `runpy` Runtime Warning on CLI Invocations
- **Status**: 🟡 Active
- **Details**: When invoking the CLI via `python -m finforge.cli.main [COMMAND]`, Python outputs:
  ```text
  <frozen runpy>:130: RuntimeWarning: 'finforge.cli.main' found in sys.modules after import of package 'finforge.cli', but prior to execution of 'finforge.cli.main'; this may result in unpredictable behaviour
  ```
- **Root Cause**: `src/finforge/cli/__init__.py` imports `main` or `app` from `finforge.cli.main`. When run as `-m finforge.cli.main`, `finforge.cli` is imported first, loading `main` into `sys.modules` before `runpy` finishes executing it as `__main__`.
- **Remediation**: Keep `src/finforge/cli/__init__.py` lightweight without eagerly importing `main`, or provide a clean `__main__.py` entrypoint inside `src/finforge/cli/`.

---

### 3.2 Rich Table Substring Truncation in Unit Tests
- **Status**: 🟢 Intermittent / Fragile
- **Details**: `tests/unit/test_cli.py::test_update_cli_pipeline_command` occasionally fails when run across different terminal window widths.
- **Root Cause**: The CLI formats output using `rich.table.Table`. When console width varies or column text is clipped into ellipsis (`cli-pipe-up...`), rigid substring assertions like `assert "cli-pipe-updater-test" in result.stdout` fail even though the command succeeded with exit code 0.
- **Remediation**: Use `runner.invoke(..., env={"COLUMNS": "200"})` to force fixed wide terminal emulations during tests, or assert on underlying JSON/data rather than formatted terminal tables.

---

## 4. Repository Cleanliness & Stray Test Artifacts

### 4.1 Ad-Hoc / Untracked Test Folders in `components/`
- **Status**: 🟡 Active
- **Details**: Running `git status` reveals multiple untracked or experimental component directories:
  - `components/bhavik/`
  - `components/hello/`
  - `components/hello1/`
- **Impact**: When `ComponentRegistry.discover()` scans `components/`, it loads these incomplete placeholder components into the global registry alongside real production components (`risk-calculator`, `text-cleaner`, etc.).
- **Remediation**: Delete or ignore scratch directories via `.gitignore` (`components/test-*`, `components/tmp-*`), and create isolated temporary directories (`tmp_path`) for CLI testing rather than writing into the workspace root.

---

## 5. Architectural & Runtime Limitations

### 5.1 Sequential-Only Execution (No Parallel Branch Execution in DAG)
- **Status**: 🟠 Architectural Limitation
- **Details**: In a DAG where Node A branches into Node B and Node C (independent parallel tasks), the current runtime executor (`finforge.runtime.executor.LocalPipelineExecutor`) executes them sequentially in topological order:
  ```text
        [Node A]
        /      \
    [Node B]  [Node C]   <-- Ran sequentially, NOT concurrently
        \      /
        [Node D]
  ```
- **Impact**: Computationally heavy scratch algorithms (like large matrix operations, clustering, or batch document embedding) cannot take advantage of multi-core CPU parallelism.
- **Planned Fix**: Implement an asynchronous / multiprocessing runtime executor (`ProcessPoolExecutor` or `asyncio.gather`) for independent sibling nodes in the DAG.

---

### 5.2 No Streaming Data Contract (Tokens / Audio / Real-Time Feeds)
- **Status**: 🟠 Design Limitation
- **Details**: All FinForge port contracts require batch, in-memory payloads (e.g., `list[float]`, `dict[str, Any]`, `str`).
- **Impact**:
  - LLM token-by-token streaming generation cannot be natively piped to downstream components or web clients.
  - Large financial tick data (millions of rows) must fit entirely in memory as Python lists/dicts, which can trigger `MemoryError`.
- **Planned Fix**: Introduce a `StreamPort` or generator contract (`Iterator[T]`) in `finforge.contracts`.

---

### 5.3 Lack of Sandbox Isolation for Dynamic Code Execution
- **Status**: ⚠️ Security Limitation
- **Details**: When `ComponentRegistry` discovers and loads components, it modifies `sys.path` and executes arbitrary Python code using `importlib.import_module()`.
- **Impact**: In an enterprise environment, if a malicious or unverified third-party component is placed into a directory, it runs with the full permissions of the host process without memory, network, or file system sandboxing.
- **Planned Fix**: Add a sandboxed subprocess runner or containerized runner mode for unverified external components.

---

## 6. Distribution & Packaging Status

### 6.1 Pre-Alpha Status & Lack of PyPI Release
- **Status**: ℹ️ Roadmap Item
- **Details**: FinForge AI is currently versioned at `0.1.0.dev0` and is not published on PyPI. Users must clone the source repository and install development dependencies manually.
- **Impact**: Requires users to have Python 3.11–3.14, Git, and virtual environment tooling pre-configured.

---

## 7. Priority Matrix & Action Items

| Priority | Issue | Location | Action Item |
| :---: | :--- | :--- | :--- |
| **P1** | Clean up scratch component directories | `components/hello1`, `components/bhavik` | Remove or add to `.gitignore` |
| **P1** | Fix `runpy` CLI warning | `src/finforge/cli/__init__.py` | Remove eager import of `main` |
| **P2** | Fix 76 Ruff linting errors | `components/`, `pipelines/` | Run `ruff check --fix` & `ruff format` |
| **P2** | Configure Mypy duplicate module handling | `pyproject.toml` | Set `explicit_package_bases = true` |
| **P3** | Stabilize CLI terminal table tests | `tests/unit/test_cli.py` | Set fixed terminal width in test runner |
| **P3** | Parallel Node Execution | `src/finforge/runtime/executor.py` | Add `ThreadPoolExecutor` / `ProcessPool` |
