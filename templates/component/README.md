# {{ component_name }}

{{ description }}

{{ author_readme_line }}
- **Category**: `{{ category }}`
- **Version**: `{{ version }}`
- **Entrypoint**: `{{ package_name }}.component:{{ class_name }}`

---

## Installation

Install in editable development mode alongside FinForge AI:

```bash
pip install -e .
```

---

## Quickstart

```python
from {{ package_name }} import {{ class_name }}

component = {{ class_name }}()
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
