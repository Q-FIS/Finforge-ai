# text-cleaner

A scratch-first text-cleaner component for FinForge AI.


- **Category**: `machine-learning`
- **Version**: `0.1.0`
- **Entrypoint**: `text_cleaner.component:TextCleanerComponent`

---

## Installation

Install in editable development mode alongside FinForge AI:

```bash
pip install -e .
```

---

## Quickstart

```python
from text_cleaner import TextCleanerComponent

component = TextCleanerComponent()
component.setup({"scale_factor": 2.0})
result = component.run({"input_data": [10.0, 20.0]}, context={})
print(result)  # {'output_data': [20.0, 40.0]}
component.teardown()
```

---

## Running Tests

Run the component test suite using pytest:

```bash
pytest tests/
```
