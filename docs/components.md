# Component Development Guide

Welcome to the FinForge AI Component Development Guide. This document explains how to author, configure, execute, and clean up components using the `BaseComponent` lifecycle contract, define declarative manifests via `component.yaml`, and enforce input/output contracts.

---

## 1. What is `BaseComponent`?

`BaseComponent` is the foundational abstract base class (`finforge.component.BaseComponent`) that defines the universal lifecycle and interface contract for all FinForge AI components.

Every component in FinForge AI—whether an educational scratch-built tokenizer, a classical decision tree, an embedding retrieval ranker, or an agent memory store—subclasses `BaseComponent` and implements its interface.

---

## 2. Why Does the Abstraction Exist?

In modern AI development, algorithms are often tightly coupled to specific frameworks or wrapped in fragmented, ad-hoc APIs:
- Machine learning libraries expect custom objects (`.fit()`, `.predict()`).
- Deep learning layers expect tensors (`.forward()`).
- LLM wrappers expect unstructured strings or bespoke message objects.
- RAG systems pass loose dictionaries or tuple results.

**`BaseComponent` establishes a uniform, library-agnostic standard:**
1. **Interoperability**: Standardized dictionary-based contracts allow disparate components to seamlessly exchange data.
2. **Predictable Lifecycle**: Standard lifecycle phases (`setup`, `run`, `teardown`) separate preparation, execution, and cleanup.
3. **Mechanical Sympathy & Algorithmic Clarity**: Developers focus on implementing core logic without mandatory dependencies on heavy runtime frameworks (such as PyTorch, Transformers, or LangChain).
4. **Drop-in Interchangeability**: A scratch-built algorithm and an optimized library implementation adhere to the exact same contract, enabling direct benchmarking and substitution.

---

## 3. The Component Lifecycle Contract

Every component follows a deterministic three-stage lifecycle:

```text
       [ UNINITIALIZED ]
              │
              │  setup(config)
              ▼
          [ READY ] ◄───────────────┐
              │                     │
              │  run(inputs, ctx)   │ repeat execution
              ▼                     │
         [ EXECUTING ] ─────────────┘
              │
              │  teardown()
              ▼
        [ TERMINATED ]
```

### Stage 1: `setup(config: dict[str, Any]) -> None`
- **Purpose**: Called once before execution to configure the component, validate parameters, and allocate resources (such as loading local weights, allocating arrays, or building lookup tables).
- **Contract**: Receives a `config` dictionary.
- **Constraints**: Must **not** perform the main data processing or compute step.
- **Error Handling**: Raises `ComponentConfigurationError` if parameters are invalid, missing, or incompatible.

### Stage 2: `run(inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]`
- **Purpose**: Executes the primary operation of the component on the provided inputs.
- **Contract**:
  - `inputs`: Dictionary containing input data conforming to the component's input schema.
  - `context`: Dictionary containing runtime context (e.g. execution trace ID, pipeline metadata, user credentials).
- **Returns**: Dictionary containing output data conforming to the component's output schema.
- **Constraints**: Must only be called after `setup()`. Must not silently return partial or corrupted data.
- **Error Handling**: Raises `ComponentLifecycleError` if called before `setup()`; raises `ComponentExecutionError` if inputs are invalid or computation fails.

### Stage 3: `teardown() -> None`
- **Purpose**: Releases acquired system resources, closes open file handles, flushes scratch buffers, or frees memory.
- **Contract**: Optional to override. The default implementation in `BaseComponent` is a safe no-op.
- **Behavior**: Subclass implementations must be **idempotent** (safe to call multiple times without error). If teardown encounters a failure, it should raise `ComponentLifecycleError` or clean up gracefully without corrupting external state.

---

## 4. Error Handling Model

FinForge AI provides a minimal, focused exception hierarchy in `finforge.exceptions`:

```text
Exception
└── FinForgeError
    ├── ComponentError
    │   ├── ComponentConfigurationError  (invalid or missing config in setup)
    │   ├── ComponentExecutionError      (invalid inputs or execution failure in run)
    │   └── ComponentLifecycleError      (invoking run before setup, or teardown failures)
    ├── ManifestError
    │   ├── ManifestNotFoundError        (manifest file missing on disk)
    │   ├── ManifestParseError           (malformed YAML, empty file, non-mapping document)
    │   └── ManifestValidationError      (schema, type, or constraint validation violations)
    ├── ContractError
    │   ├── ContractValidationError      (runtime inputs or outputs violate schema types/bounds)
    │   └── PortIncompatibleError        (static port connection mismatch or narrowing violation)
    ├── RegistryError
    │   ├── ComponentNotFoundError       (lookup of unregistered component name)
    │   ├── ComponentRegistrationError   (invalid class, manifest, or entrypoint mismatch)
    │   └── DuplicateComponentError      (registering an existing component without overwrite=True)
    ├── TemplateError
    │   ├── TemplateNotFoundError        (template directory or file missing)
    │   └── TemplateRenderError          (missing token in substitution context)
    └── ProjectGenerationError
        ├── DestinationExistsError       (target destination directory already exists)
        ├── InvalidIdentifierError       (component, package, or class name is invalid)
        └── PathTraversalError           (target path escapes destination root)
```

Never silently swallow exceptions in component implementations or validation routines. Always raise clear, actionable errors with source and field attribution.

---

## 5. How to Author a Custom Component

### Step-by-Step Walkthrough

1. Import `BaseComponent` and relevant exceptions:
   ```python
   from typing import Any
   from finforge import (
       BaseComponent,
       ComponentConfigurationError,
       ComponentExecutionError,
       ComponentLifecycleError,
   )
   ```

2. Inherit from `BaseComponent` and define initial state in `__init__()`:
   ```python
   class MultiplierComponent(BaseComponent):
       def __init__(self) -> None:
           self._factor: float = 1.0
           self._is_setup: bool = False
   ```

3. Implement `setup(config)`:
   ```python
   def setup(self, config: dict[str, Any]) -> None:
       if not isinstance(config, dict):
           raise ComponentConfigurationError("Config must be a dictionary.")
       if "factor" not in config:
           raise ComponentConfigurationError("Missing required config: 'factor'")
       if not isinstance(config["factor"], (int, float)):
           raise ComponentConfigurationError("Config 'factor' must be a numeric value.")
       self._factor = float(config["factor"])
       self._is_setup = True
   ```

4. Implement `run(inputs, context)`:
   ```python
   def run(
       self,
       inputs: dict[str, Any],
       context: dict[str, Any],
   ) -> dict[str, Any]:
       if not self._is_setup:
           raise ComponentLifecycleError("Call setup() before run().")
       if not isinstance(inputs, dict) or "value" not in inputs:
           raise ComponentExecutionError("Inputs must be a dict containing 'value'.")

       value = inputs["value"]
       if not isinstance(value, (int, float)):
           raise ComponentExecutionError("Input 'value' must be numeric.")

       result = value * self._factor
       return {
           "result": result,
           "factor_applied": self._factor,
           "trace_id": (context.get("trace_id") if isinstance(context, dict) else None),
       }
   ```

5. Implement `teardown()` (optional):
   ```python
       def teardown(self) -> None:
           self._is_setup = False
           self._factor = 1.0
   ```

---

## 6. Complete Minimal Example (`ExampleComponent`)

FinForge AI ships with `ExampleComponent` (`finforge.example.ExampleComponent`), a fully tested reference implementation:

```python
from finforge import ExampleComponent

# 1. Instantiate
component = ExampleComponent()

# 2. Configure & initialize
component.setup({"mode": "uppercase", "prefix": "OUTPUT: "})

# 3. Execute with inputs and runtime context
outputs = component.run(
    inputs={"text": "hello world"}, context={"execution_id": "run-001"}
)

print(outputs)
# Output:
# {
#     "result": "OUTPUT: HELLO WORLD",
#     "length": 19,
#     "mode": "uppercase",
#     "execution_id": "run-001"
# }

# 4. Clean up
component.teardown()
```

---

## 7. Component Manifest Specification (`component.yaml`)

### Why `component.yaml` Exists
Every FinForge AI component is declaratively described by a manifest file named `component.yaml`. This file establishes static metadata without executing any Python code:
- **Zero-Execution Introspection**: Tools, registries, and linters inspect input/output ports and configuration schemas safely without importing dependencies or running untrusted code.
- **Port Compatibility**: Guarantees producer and consumer schema compatibility during graph assembly.
- **Dependency Isolation**: Explicitly lists PEP 508 runtime package dependencies.

### Manifest Schema Overview

```yaml
name: custom-kmeans
version: "0.1.0"
description: K-Means clustering algorithm implemented from scratch with Lloyd's iteration.

api_version: "1"
category: machine-learning

entrypoint: my_kmeans.component:KMeansComponent

inputs:
  data:
    type: array
    required: true
    items:
      type: number
    description: Input feature matrix of shape (n_samples, n_features).

outputs:
  labels:
    type: array
    items:
      type: integer
    description: Cluster assignments for each input sample.
  centroids:
    type: array
    description: Coordinates of cluster centroids.

config:
  n_clusters:
    type: integer
    default: 3
    description: The number of clusters to form.
  max_iter:
    type: integer
    default: 300
    description: Maximum iterations.
  tol:
    type: float
    default: 0.0001
    description: Relative tolerance convergence criterion.

dependencies:
  - numpy>=2.0.0
```

### Manifest Fields Explained

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | **Yes** | Slug-like component identifier (lowercase alphanumeric, hyphens, underscores). |
| `version` | `string` | **Yes** | PEP 440 compliant semantic version (e.g. `"0.1.0"`, `"1.2.0a1"`). |
| `description` | `string` | **Yes** | Non-empty summary of what the component does. |
| `api_version` | `string` | **Yes** | Manifest specification version (currently `"1"`). |
| `category` | `string` | **Yes** | Recognized AI domain: `machine-learning`, `classical-ml`, `deep-learning`, `llm`, `rag`, `agentic`, `agents`, `multimodal`, `data-processing`, `evaluation`. |
| `entrypoint` | `string` | **Yes** | Target Python class formatted as `<module_path>:<class_name>` (not imported during parsing). |
| `inputs` | `mapping` | No | Map of input port names to port definitions (defaults to `{}`). |
| `outputs` | `mapping` | No | Map of output port names to port definitions (defaults to `{}`). |
| `config` | `mapping` | No | Map of configuration parameter keys to config definitions (defaults to `{}`). |
| `dependencies` | `list` | No | List of PEP 508 dependency strings (defaults to `[]`). |

### Supported Port Data Types
Ports (`inputs` and `outputs`) declare standardized types:
- `string`: Unicode character strings.
- `integer`: 64-bit integer numbers (booleans are strictly rejected as integers).
- `number` / `float`: Scalar numeric numbers (accepts integers and floats; rejects booleans).
- `boolean`: Boolean `true` or `false`.
- `array`: Homogeneous lists or N-dimensional array structures. Supports optional `items` specification.
- `object`: Structured mapping or key-value dictionary.
- `tensor`: Deep learning tensor representations.
- `dataframe`: Tabular data structures.
- `binary`: Raw byte buffers.
- `any`: Arbitrary typed payloads.

---

## 8. Input/Output Contract Validation Engine

FinForge AI provides a dedicated validation engine in `finforge.contracts` to verify runtime data conformity and validate static connection compatibility between components.

### What are Contracts and Why are They Needed?
Contracts are formal, machine-readable specifications governing the data entering and leaving a component:
- **Prevent Silent Data Corruption**: Catches type mismatches (such as booleans passed where integers are required, or strings passed where arrays are expected) before downstream computations fail unexpectedly.
- **Zero-Execution Pipeline Wiring**: Allows pipeline composition engines to statically check whether component outputs are compatible with inputs without running heavyweight models.
- **Self-Documenting Code**: Contracts make component requirements explicit to developers and automated testing harnesses.

### 1. Runtime Input Validation (`validate_inputs`)

Validates runtime input dictionaries passed to `component.run()`:
- **Required Ports**: All ports declared with `required: true` (the default) must be present in the data.
- **Optional Ports**: Ports with `required: false` may be omitted without error.
- **Unexpected Keys**: Extra keys not declared in the component schema are rejected by default.
- **Type Checking**: Values must match their declared types. For `array` ports declaring `items`, every element is validated recursively.
- **Non-Mutation**: The validator never modifies user input dictionaries.

```python
from finforge.contracts import validate_inputs
from finforge.manifest import PortDefinition

schema = {
    "data": PortDefinition(
        type="array", required=True, items=PortDefinition(type="number")
    ),
    "max_iter": PortDefinition(type="integer", required=False),
}

# Valid inputs
validate_inputs({"data": [1.0, 2.5, 3.0]}, schema)

# Invalid: missing required port
# Raises ContractValidationError("Missing required input 'data'...")

# Invalid: boolean passed as integer
# Raises ContractValidationError("Invalid type for 'max_iter': expected 'integer', got 'boolean'...")
```

### 2. Runtime Output Validation (`validate_outputs`)

Validates dictionary outputs emitted by `component.run()` before they are forwarded to downstream components:
- **Required Outputs**: Required output ports must be present in the returned dictionary.
- **Type Conformity**: Returned values must conform strictly to output port definitions.
- **Unexpected Outputs**: Unregistered keys in output dictionaries are rejected to prevent state pollution.
- **Non-Mutation**: The validator never mutates output data.

### 3. Static Port Compatibility (`check_port_compatibility`)

Verifies whether a producer's output port can safely pipe data into a consumer's input port at graph-construction time:

```python
from finforge.contracts import check_port_compatibility, is_port_compatible
from finforge.manifest import PortDefinition

source_output = PortDefinition(type="integer")
target_input = PortDefinition(type="number")

# Integer output promoted to number input: Compatible
assert is_port_compatible(source_output, target_input) is True

# Number output narrowed to integer input: Rejected (loss of precision)
assert is_port_compatible(target_input, source_output) is False
```

### Type Compatibility and Promotion Hierarchy

```text
    ┌──────────┐
    │  integer │ ────(widens to)───► ┌────────────────┐
    └──────────┘                     │ number / float │ ────(widens to)───► ┌─────┐
                                     └────────────────┘                     │ any │
    ┌──────────┐                                                            └─────┘
    │  string  │ ─────────────────────────────────────────────────────────►    ▲
    └──────────┘                                                               │
    ┌──────────┐                                                               │
    │  object  │ ─────────────────────────────────────────────────────────►    │
    └──────────┘                                                               │
    ┌──────────┐                                                               │
    │  array   │ ────(exact or compatible items)──────────────────────────►    │
    └──────────┘                                                               │
```

- **Exact Type Match**: Always compatible (`string` -> `string`, `object` -> `object`).
- **Numeric Promotion**: `integer` output promotes to `number` or `float` input.
- **No Narrowing**: `number` or `float` output **cannot** connect to `integer` input.
- **Array Items**: When both ports define `items`, compatibility is evaluated recursively on the item definitions.
- **Incompatible Types**: Mismatched types (e.g. `string` -> `array`, `boolean` -> `integer`) are rejected with `PortIncompatibleError`.
- **Zero Execution**: Compatibility validation operates solely on metadata and never executes components.

---

## 9. Component Registry

FinForge AI provides an in-memory component catalog via `finforge.registry.ComponentRegistry`. The registry pairs validated `ComponentManifest` declarations with concrete `BaseComponent` classes to provide deterministic registration, retrieval, inspection, and catalog management for pipeline orchestration.

### Key Principles

1. **Class-Only Storage**: The registry manages component classes, not instances. Component instantiation and execution remain strictly decoupled from registration.
2. **Deterministic Validation**:
   - Component classes must inherit from `BaseComponent`.
   - Manifests must be validated `ComponentManifest` instances.
   - The manifest's `entrypoint` class name (e.g. `path.to.module:KMeansComponent`) must strictly match the component class's `__name__`.
3. **No Hidden Code Execution**: Registering a component never invokes `setup()`, `run()`, `teardown()`, or `__init__()`.
4. **Collision Prevention**: Duplicate registrations are rejected by default with `DuplicateComponentError`. Overwriting requires passing `overwrite=True` explicitly.
5. **Defensive Immutability**: All retrieval operations return deep copies of registered manifests to ensure external modifications cannot corrupt internal registry state.

### Registration and Retrieval API

```python
from finforge.component import BaseComponent
from finforge.manifest import load_manifest
from finforge.registry import ComponentRegistry

# Initialize in-memory registry
registry = ComponentRegistry()

# Load manifest and register component class
manifest = load_manifest("components/my_kmeans/component.yaml")
registry.register(component_class=KMeansComponent, manifest=manifest)

# Check existence
if "my-kmeans" in registry:
    print("KMeansComponent is available!")

# Retrieve component class or manifest
cls = registry.get("my-kmeans")
manifest_copy = registry.get_manifest("my-kmeans")
entry = registry.get_entry("my-kmeans")  # Returns RegistryEntry

# Filter and list components
all_names = registry.list_components()
ml_components = registry.list_components(category="machine-learning")
all_manifests = registry.list_manifests()

# Unregister or clear
registry.unregister("my-kmeans")
registry.clear()
```

### Registry Entry

Each registered component is stored internally as a frozen `RegistryEntry`:

```python
@dataclass(frozen=True)
class RegistryEntry:
    name: str
    component_class: type[BaseComponent]
    manifest: ComponentManifest
```

---

## 10. Component Project Scaffolding & SDK Utilities

FinForge AI provides an automated project scaffolding utility in `finforge.sdk` to help developers rapidly bootstrap independent, standardized component packages from scratch.

### Why Does the Component Template Exist?

Authoring a production-ready component involves boilerplate configuration:
- Creating a declarative `component.yaml` manifest conforming to FF-02 schema.
- Structuring a standard `src/` layout with Hatchling packaging (`pyproject.toml`).
- Implementing `BaseComponent` lifecycle methods (`setup`, `run`, `teardown`).
- Authoring pytest test suites enforcing lifecycle invariants.
- Providing usage examples and Markdown documentation.

The template system eliminates manual setup errors, ensures immediate compliance with FinForge contracts, and lets developers focus on implementing their algorithmic logic.

> [!NOTE]
> The SDK utilities documented here (`finforge.sdk.create_component_project`) provide programmatic Python scaffolding. The terminal command (`finforge create`) is a separate CLI abstraction scheduled for Step 7 (FF-06).

### Generated Directory Structure

```text
my-component/
├── component.yaml            # Declarative component manifest (FF-02 schema)
├── pyproject.toml            # Independent package build definition (PEP 517/621)
├── README.md                 # Quickstart, installation, and usage documentation
├── src/
│   └── my_component/
│       ├── __init__.py       # Package boundary exporting component class
│       └── component.py      # BaseComponent implementation with lifecycle hooks
├── tests/
│   └── test_component.py     # Pytest test suite checking setup, run, and contracts
└── examples/
    └── basic_usage.py        # Executable sample script demonstrating execution
```

### Template Variables and Naming Rules

The SDK accepts the following parameters and normalizes them safely:

| Variable | Description | Default / Normalization Rule |
| :--- | :--- | :--- |
| `component_name` | Slug-like identifier for component. | Lowercase alphanumeric with single hyphens/underscores (e.g. `custom-kmeans`). |
| `package_name` | Python import package name. | Derived from `component_name` (`custom_kmeans`). Must be a valid Python identifier. |
| `class_name` | Python component class name. | Derived from `component_name` (`CustomKmeansComponent`). Must be PascalCase. |
| `category` | AI/ML domain category. | Must be in `SUPPORTED_CATEGORIES` (default: `machine-learning`). |
| `version` | Initial package version. | Must follow PEP 440 (default: `0.1.0`). |
| `description` | Summary of component. | Defaults to `"A scratch-first <name> component for FinForge AI."` |
| `author` | Author credit. | Optional. Left empty if not explicitly provided (no invented author details). |

### Programmatic Scaffolding API

```python
from pathlib import Path
from finforge.sdk import create_component_project

project_path = create_component_project(
    name="custom-kmeans",
    destination=Path("./components"),
    description="Scratch-built K-Means algorithm using Lloyd's method.",
    category="machine-learning",
    version="0.1.0",
    author="FinForge Developer",
)

print(f"Scaffolded component at: {project_path}")
```

### Safety and Security Guarantees

1. **Collision Protection**: If the destination folder already exists, `DestinationExistsError` is raised immediately. Pre-existing files are never touched or modified.
2. **Path Traversal Protection**: Names containing `..`, `/`, `\`, or absolute path indicators are rejected with `InvalidIdentifierError` or `PathTraversalError`.
3. **Zero Code Execution**: Generating a component project creates files on disk but never imports, executes, or instantiates the generated component code.

### Developing and Testing the Generated Component

1. **Install in editable mode**:
   ```bash
   cd components/custom-kmeans
   pip install -e .
   ```
2. **Execute tests**:
   ```bash
   pytest tests/
   ```
3. **Implement custom algorithm**: Open `src/custom_kmeans/component.py` and replace the placeholder logic inside `run()`:
   ```python
   # TODO: Implement your custom algorithm or data processing logic here.
   ```

---

## 11. Component Testing Engine

FinForge AI provides an automated testing engine in `finforge.testing` designed to verify that custom components conform to FinForge architectural contracts, lifecycle invariants, and schema requirements.

### Distinction: Framework Validation vs. Developer Tests

The engine strictly separates two complementary testing responsibilities:

1. **Framework Validation**:
   - Programmatically orchestrated by FinForge.
   - Evaluates whether the component satisfies architectural constraints: valid `component.yaml` manifest, standard package structure, subclassing of `BaseComponent`, declared input/output contract enforcement, and lifecycle state management (`setup` -> `run` -> `teardown`).
   - Guarantees deterministic cleanup: `teardown()` is invoked in a `finally` block even if `setup()` or `run()` fails.

2. **Developer-Provided Pytest Execution**:
   - Discovers and executes custom algorithmic and unit tests authored by the component developer (typically located in the component's `tests/` directory).
   - Executed in an isolated subprocess (`sys.executable -m pytest`) with `PYTHONPATH` explicitly configured to prevent in-process namespace collisions.
   - Collects test counts, execution durations, and failure tracebacks.

### Programmatic Testing API

```python
from pathlib import Path
from finforge.testing import run_component_tests

# Run all framework validation stages and developer pytest tests
result = run_component_tests(
    component_path=Path("./components/custom-kmeans"),
    test_inputs={"features": [[1.0, 2.0], [3.0, 4.0]]},  # Optional custom inputs
    test_config={"n_clusters": 2},  # Optional custom config
    run_developer_tests=True,  # Set to False to skip pytest
)

print(f"Overall status: {result.status.value}")
print(f"Passed: {result.passed}")
print(f"Total duration: {result.duration_ms:.2f}ms")

# Inspect individual validation stages
for stage in result.stages:
    print(
        f"[{stage.status.value}] {stage.stage_name}: {stage.message} ({stage.duration_ms:.2f}ms)"
    )

# Inspect developer test summary (if executed)
if result.developer_tests:
    dev = result.developer_tests
    print(
        f"Developer tests: {dev.passed_count} passed, {dev.failed_count} failed in {dev.duration_ms:.2f}ms"
    )
```

### CLI Command: `finforge test`

The testing engine is integrated directly into the developer CLI:

```bash
# Test a component and display rich formatted output
finforge test ./components/custom-kmeans

# Skip developer pytest suite and only perform framework validation
finforge test ./components/custom-kmeans --skip-developer-tests

# Output machine-readable JSON for CI/CD pipelines
finforge test ./components/custom-kmeans --json
```

### Execution Safety & Sandboxing Limitations

> [!IMPORTANT]
> **Trusted Code Only**: The testing engine executes component code locally and runs developer test suites via subprocess (`shell=False`).
> FinForge AI does **not** provide sandbox security against malicious or untrusted code in v0.1. Running `finforge test` on an untrusted component executes arbitrary Python code with the permissions of the current user.
>
> **Sandboxing Roadmap**:
> - **v0.1**: Local process execution of trusted components.
> - **v0.2+**: Containerized test runner (Docker / Podman) and restricted microVM execution for untrusted community components.
> - **Future**: WebAssembly (Wasm/WASI) sandboxed runtimes for lightweight, dependency-free component validation.

---

## 12. Current State vs. Future Capabilities

| Capability | Current State (v0.1 / FF-01 through FF-07) | Planned Future Milestone |
|---|---|---|
| **Base Interface** | Implemented (`BaseComponent` ABC with `setup`, `run`, `teardown`). | Extended streaming / async hooks (`run_async`). |
| **Manifest System** | Implemented (`ComponentManifest` Pydantic v2 schema & `load_manifest` parser). | Automated manifest generator CLI (`finforge component new`). |
| **Contract Validation** | Implemented (`validate_inputs`, `validate_outputs`, `check_port_compatibility`). | Automated pipeline graph construction validation. |
| **Component Registry** | Implemented (`ComponentRegistry` in-memory catalog with metadata indexing). | Automated filesystem scanning and dynamic module loading. |
| **Project Scaffolding** | Implemented (`finforge.sdk.create_component_project` & CLI `finforge create`). | Component publishing and remote template repositories. |
| **CLI Tooling** | Implemented (`finforge --version`, `finforge --help`, `finforge create`, `finforge test`). | Pipeline execution commands (`finforge pipeline run`). |
| **Component Testing** | Implemented (`run_component_tests`, `finforge test`, multi-stage validation, pytest runner). | Sandboxed containerized validation for community registry submissions. |
| **Error Handling** | Implemented (`FinForgeError`, `ComponentError`, `ManifestError`, `ContractError`, `RegistryError`, `TemplateError`, `TestingError`, `ComponentValidationError`, `TestExecutionError`). | Diagnostics telemetry and visual error reporting. |
| **Execution** | Manual invocation (`component.setup(cfg)`, `component.run(inp, ctx)`). | Automated pipeline builder and DAG runtime executor. |
| **Discovery** | Direct registration and explicit manifest loading. | Workspace filesystem scanning and local registry indexing CLI. |
