# Contributing to FinForge AI

Thank you for your interest in contributing to **FinForge AI**!

FinForge AI is an open-source, modular AI development framework built on a **scratch-first** philosophy: enabling developers, students, and researchers to understand, implement, and compose AI components from first principles.

Whether you are fixing a typo, improving documentation, designing interfaces, or authoring components, your contributions are welcome.

---

## Code of Conduct

All contributors and maintainers are expected to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before participating.

---

## Core Development Philosophy

Before contributing code, keep our core architectural principles in mind:

1. **Scratch-First Mindset**: Prioritize clarity, first-principles algorithmic implementation, and educational value over opaque wrappers around third-party libraries.
2. **Lightweight Core**: The core framework must remain lean. Heavy frameworks (such as PyTorch, TensorFlow, Transformers, or LangChain) must **never** be mandatory dependencies of the core package. They may only be optional extras or component-specific dependencies.
3. **Strict Contracts & Typings**: Components interact through standardized interfaces and validated Pydantic schemas. Every public API must be strictly typed.
4. **General-Purpose AI**: Despite the finance-inspired project name, FinForge AI is a domain-agnostic framework supporting Classical ML, Deep Learning, LLMs, RAG, Agentic AI, and Multimodal systems.

---

## Development Setup

### Prerequisites

- **Python**: Version 3.11 or newer (Python 3.11, 3.12, 3.13 supported).
- **Git**: Installed and configured.
- Recommended tool: [`uv`](https://docs.astral.sh/uv/) for fast virtual environment and dependency management (standard `python -m venv` and `pip` are also fully supported).

### Setup Steps

1. **Fork and clone the repository:**

   ```bash
   git clone https://github.com/finforge-ai/finforge-ai.git
   cd finforge-ai
   ```

2. **Create and activate a virtual environment:**

   *Using standard venv:*
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

   *Or using `uv`:*
   ```bash
   uv venv
   source .venv/bin/activate
   ```

3. **Install the package in editable mode with development dependencies:**

   ```bash
   pip install -r requirements-dev.txt
   # Or directly:
   pip install -e ".[dev]"
   ```

4. **Verify the installation:**

   ```bash
   finforge --version
   pytest
   ```

---

## Quality Standards

All pull requests must pass our automated quality checks:

### Code Formatting & Linting (Ruff)

We use [Ruff](https://docs.astral.sh/ruff/) for fast formatting and linting:

```bash
# Check formatting
ruff format --check .

# Automatically apply formatting
ruff format .

# Check lint rules
ruff check .

# Automatically fix autofixable lint issues
ruff check --fix .
```

### Static Type Checking (MyPy)

We enforce strict MyPy typing across all codebase modules:

```bash
mypy
```

### Running Tests (Pytest)

Run the test suite using pytest:

```bash
# Run all unit tests
pytest

# Run with verbose output and coverage
pytest -v --cov=finforge
```

---

## Contribution Workflow

1. **Check existing issues and discussions:**
   - Search open [Issues](https://github.com/finforge-ai/finforge-ai/issues) and [Discussions](https://github.com/finforge-ai/finforge-ai/discussions) before starting work.
   - For major features or architectural proposals, open a Feature Request or Discussion first to align on design.

2. **Branch naming conventions:**
   - `feat/feature-name` for new capabilities or components
   - `fix/bug-description` for bug fixes
   - `docs/topic-name` for documentation updates
   - `refactor/scope` for non-behavioral code restructuring

3. **Commit guidelines:**
   - Write clear, concise, imperative commit messages:
     - `feat: add component manifest schema validation`
     - `fix: resolve cli version argument parsing error`
     - `docs: update architecture overview for local runtime`

4. **Submitting a Pull Request:**
   - Ensure linting, typing, and all tests pass locally.
   - Reference any relevant issues in the PR description (e.g., `Closes #123`).
   - Keep pull requests focused on a single change or feature.

---

## Repository Structure

```text
finforge-ai/
├── .github/              # Issue templates, CI/CD workflows
├── components/examples/  # Example scratch-built components
├── docs/                 # Architectural specifications and guides
├── examples/             # End-to-end runnable examples
├── scripts/              # Developer automation scripts
├── src/
│   └── finforge/         # Core framework package source
├── templates/component/  # Starter scaffolding for new components
└── tests/
    ├── integration/      # Integration test suite
    └── unit/             # Unit test suite
```

---

## Community and Questions

If you have questions, encounter ambiguities, or wish to propose new ideas:
- Open a topic on [GitHub Discussions](https://github.com/finforge-ai/finforge-ai/discussions).
- File an issue on [GitHub Issues](https://github.com/finforge-ai/finforge-ai/issues).
