"""Demonstration script for RiskCalculatorComponent."""

import sys
from pathlib import Path

# Add component's src to path so Python can find risk_calculator
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from risk_calculator.component import RiskCalculatorComponent


def main() -> None:
    print("=== FinForge AI: Risk Calculator Demonstration ===")

    # 1. Instantiate
    calculator = RiskCalculatorComponent()

    # 2. Setup with custom config (flag transactions over $5,000 as HIGH risk)
    config = {"threshold": 5000.0}
    calculator.setup(config)
    print(f"✓ Component initialized with threshold = ${config['threshold']:,.2f}")

    # 3. Run with test transactions
    test_transactions = [
        {"amount": 120.50},
        {"amount": 4999.00},
        {"amount": 5000.00},
        {"amount": 7500.00},
        {"amount": 25000.00},
    ]

    print("\nEvaluating transactions:")
    for tx in test_transactions:
        result = calculator.run(inputs=tx, context={})
        amt = tx["amount"]
        level = result["risk_level"]
        print(f"  Transaction: ${amt:>9.2f}  -->  Risk Level: {level}")

    # 4. Teardown
    calculator.teardown()
    print("\n✓ Resources released and teardown complete.")


if __name__ == "__main__":
    main()
