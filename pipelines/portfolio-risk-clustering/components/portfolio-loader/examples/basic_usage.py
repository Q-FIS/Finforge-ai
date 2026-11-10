"""Basic usage example for PortfolioLoaderComponent."""

from portfolio_loader.component import PortfolioLoaderComponent


def main() -> None:
    # 1. Instantiate component
    component = PortfolioLoaderComponent()

    # 2. Configure component
    config = {"scale_factor": 3.0}
    component.setup(config)
    print(f"Configured PortfolioLoaderComponent with {config}")

    # 3. Execute component
    inputs = {"input_data": [1.0, 2.0, 3.0]}
    context = {"execution_id": "example-run-1"}
    output = component.run(inputs, context)
    print(f"Inputs: {inputs}")
    print(f"Outputs: {output}")

    # 4. Clean up
    component.teardown()
    print("Execution complete and resources released.")


if __name__ == "__main__":
    main()
