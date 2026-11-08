"""Component scaffolding and project generation SDK utility."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from finforge.exceptions import (
    DestinationExistsError,
    PathTraversalError,
    ProjectGenerationError,
    TemplateNotFoundError,
)
from finforge.manifest.models import SUPPORTED_CATEGORIES
from finforge.sdk.normalization import (
    normalize_component_name,
    to_class_name,
    to_package_name,
)
from finforge.sdk.template import (
    get_default_template_dir,
    render_template_path_segment,
    render_template_string,
)


def create_component_project(
    name: str,
    destination: str | Path = ".",
    *,
    description: str | None = None,
    category: str = "machine-learning",
    version: str = "0.1.0",
    author: str | None = None,
    package_name: str | None = None,
    class_name: str | None = None,
    template_dir: str | Path | None = None,
) -> Path:
    """Generate a complete, independent FinForge component project directory.

    Args:
        name: Desired component name (e.g. 'custom-kmeans', 'my-rag-agent').
        destination: Parent directory where the component folder will be created.
            Defaults to current working directory.
        description: Optional human summary of the component.
        category: AI/ML discipline category (must be a valid FinForge category).
        version: Initial PEP 440 version string (default: '0.1.0').
        author: Optional author name. Left empty if not explicitly provided.
        package_name: Optional explicit Python package name. If omitted, derived
            automatically from the component name.
        class_name: Optional explicit Python class name. If omitted, derived
            automatically from the component name.
        template_dir: Optional explicit path to a component template directory.
            If omitted, uses the framework default template.

    Returns:
        The resolved Path of the created component project directory.

    Raises:
        InvalidIdentifierError: If component, package, or class name is invalid.
        DestinationExistsError: If the target project directory already exists.
        PathTraversalError: If target path escapes the destination root.
        ProjectGenerationError: If validation or generation fails.
        TemplateNotFoundError: If the template directory does not exist.
        TemplateRenderError: If template rendering encounters missing variables.
    """
    # 1. Normalize component name
    norm_name = normalize_component_name(name)

    # 2. Derive or validate package name
    if package_name is not None:
        if not isinstance(package_name, str):
            raise ProjectGenerationError("Package name must be a string.")
        resolved_package = to_package_name(package_name)
    else:
        resolved_package = to_package_name(norm_name)

    # 3. Derive or validate class name
    if class_name is not None:
        if not isinstance(class_name, str):
            raise ProjectGenerationError("Class name must be a string.")
        resolved_class = to_class_name(class_name, suffix="")
    else:
        resolved_class = to_class_name(norm_name)

    # 4. Validate category
    norm_category = category.strip().lower()
    if norm_category not in SUPPORTED_CATEGORIES:
        valid_cats = ", ".join(sorted(SUPPORTED_CATEGORIES))
        raise ProjectGenerationError(
            f"Unsupported category '{category}'. "
            f"Supported categories are: {valid_cats}."
        )

    # 5. Validate version format
    clean_version = str(version).strip()
    try:
        Version(clean_version)
    except InvalidVersion as err:
        raise ProjectGenerationError(
            f"Invalid version format '{version}'. Must follow PEP 440."
        ) from err

    # 6. Description & Author handling
    resolved_description = (
        description.strip()
        if description and description.strip()
        else f"A scratch-first {norm_name} component for FinForge AI."
    )

    clean_author = author.strip() if author and author.strip() else ""
    if clean_author:
        authors_block = f'authors = [\n    {{ name = "{clean_author}" }},\n]'
        author_readme_line = f"- **Author**: {clean_author}"
    else:
        authors_block = "authors = []"
        author_readme_line = ""

    # 7. Destination and Traversal safety
    dest_path = Path(destination).resolve()
    target_dir = (dest_path / norm_name).resolve()

    try:
        target_dir.relative_to(dest_path)
    except ValueError as err:
        raise PathTraversalError(
            f"Invalid target path '{target_dir}': "
            f"escapes destination root '{dest_path}'."
        ) from err

    if target_dir.exists():
        raise DestinationExistsError(
            f"Destination directory already exists: '{target_dir}'. "
            "Refusing to overwrite existing user files."
        )

    # 8. Resolve template directory
    if template_dir is not None:
        tpl_path = Path(template_dir).resolve()
        if not tpl_path.is_dir():
            raise TemplateNotFoundError(
                f"Specified template directory does not exist: '{tpl_path}'."
            )
    else:
        tpl_path = get_default_template_dir()

    # 9. Build render context
    context: dict[str, Any] = {
        "component_name": norm_name,
        "package_name": resolved_package,
        "class_name": resolved_class,
        "description": resolved_description,
        "category": norm_category,
        "version": clean_version,
        "author": clean_author,
        "authors_block": authors_block,
        "author_readme_line": author_readme_line,
    }

    # 10. Generate project files
    created_target = False
    try:
        target_dir.mkdir(parents=True, exist_ok=False)
        created_target = True

        for item in sorted(tpl_path.rglob("*")):
            if item.name == ".gitkeep":
                continue

            rel_path = item.relative_to(tpl_path)
            rendered_parts = [
                render_template_path_segment(part, context) for part in rel_path.parts
            ]
            dest_item = target_dir.joinpath(*rendered_parts).resolve()

            # Verify individual item path does not escape target directory
            try:
                dest_item.relative_to(target_dir)
            except ValueError as err:
                raise PathTraversalError(
                    f"Rendered path '{dest_item}' escapes target "
                    f"directory '{target_dir}'."
                ) from err

            if item.is_dir():
                dest_item.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                dest_item.parent.mkdir(parents=True, exist_ok=True)
                raw_text = item.read_text(encoding="utf-8")
                rendered_text = render_template_string(raw_text, context)
                dest_item.write_text(rendered_text, encoding="utf-8")

    except Exception:
        # Safe cleanup: If error occurs during generation, remove created directory
        if created_target and target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise

    return target_dir
