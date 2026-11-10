# hello1

A scratch-first hello1 component for FinForge AI.


- **Category**: `machine-learning`
- **Version**: `0.1.0`
- **Entrypoint**: `hello1.component:Hello1Component`

---

## Installation

Install in editable development mode alongside FinForge AI:

```bash
pip install -e .
```

---

## Quickstart

```python
from hello1 import Hello1Component

component = Hello1Component()
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
