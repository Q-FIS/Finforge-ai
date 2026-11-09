# risk-calculator

A scratch-first risk evaluation component for FinForge AI.

- **Category**: `machine-learning`
- **Version**: `0.1.0`
- **Entrypoint**: `risk_calculator.component:RiskCalculatorComponent`

---

## Quickstart

```python
from risk_calculator.component import RiskCalculatorComponent

component = RiskCalculatorComponent()
component.setup({"threshold": 5000.0})
result = component.run({"amount": 7500.0}, context={})
print(result)  # {'risk_level': 'HIGH'}
component.teardown()
```
