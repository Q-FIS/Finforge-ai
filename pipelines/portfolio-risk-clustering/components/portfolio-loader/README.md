# portfolio-loader

Loads asset risk metrics and volumes


- **Category**: `machine-learning`
- **Version**: `0.1.0`
- **Entrypoint**: `portfolio_loader.component:PortfolioLoaderComponent`

---

## Installation

Install in editable development mode alongside FinForge AI:

```bash
pip install -e .
```

---

## Quickstart

```python
from portfolio_loader import PortfolioLoaderComponent

component = PortfolioLoaderComponent()
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
