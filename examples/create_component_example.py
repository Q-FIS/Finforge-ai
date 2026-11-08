"""Demonstration of using the FinForge Component SDK to generate a component project."""

import tempfile
from pathlib import Path

from finforge.manifest import load_manifest
from finforge.sdk import create_component_project


def main() -> None:
    print("=== FinForge AI Component Scaffolding Demonstration ===")

    with tempfile.TemporaryDirectory() as tmp_dir:
        destination = Path(tmp_dir) / "workspace"
        destination.mkdir(parents=True, exist_ok=True)

        print(f"\n1. Target destination directory: {destination}")

        # 2. Generate component project using SDK API
        print("\n2. Generating 'my-scratch-kmeans' component project...")
        project_dir = create_component_project(
            name="my-scratch-kmeans",
            destination=destination,
            description="Scratch-built K-Means algorithm using Lloyd's method.",
            category="machine-learning",
            version="0.1.0",
            author="FinForge Developer",
        )

        print(f"✓ Project generated successfully at: {project_dir}")

        # 3. Inspect generated project structure
        print("\n3. Generated Directory Structure:")
        for item in sorted(project_dir.rglob("*")):
            rel_path = item.relative_to(project_dir)
            prefix = "📁" if item.is_dir() else "📄"
            print(f"   {prefix} {rel_path}")

        # 4. Verify manifest loads cleanly with existing FF-02 parser
        print("\n4. Validating generated manifest...")
        manifest_path = project_dir / "component.yaml"
        manifest = load_manifest(manifest_path)
        print(f"   - Name: {manifest.name}")
        print(f"   - Category: {manifest.category}")
        print(f"   - Version: {manifest.version}")
        print(f"   - Entrypoint: {manifest.entrypoint}")
        print("✓ Component manifest parsed and validated with zero execution.")

    print("\n✓ Scaffolding demonstration completed cleanly.")


if __name__ == "__main__":
    main()
