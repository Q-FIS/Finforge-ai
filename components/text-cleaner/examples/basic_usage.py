"""Basic usage example for TextCleanerComponent."""

from text_cleaner.component import TextCleanerComponent


def main() -> None:
    # 1. Instantiate component
    component = TextCleanerComponent()

    # 2. Configure component
    config = {"lowercase": True}

    component.setup(config)
    print(f"Configured TextCleanerComponent with {config}")

    # 3. Execute component
    inputs = {
        "input_data": "  Hello     FinForge   AI! \n Welcome to   Text Cleaning.  "
    }

    context = {"execution_id": "example-run-1"}

    output = component.run(inputs, context)

    print(f"\nInputs: {inputs}")
    print(f"Outputs: {output}")

    # 4. Clean up
    component.teardown()
    print("\nExecution complete and resources released.")


if __name__ == "__main__":
    main()
