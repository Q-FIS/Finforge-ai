"""Template loading and token rendering engine for FinForge component scaffolding."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from finforge.exceptions import TemplateNotFoundError, TemplateRenderError

_TOKEN_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def get_default_template_dir() -> Path:
    """Locate the default component template directory.

    Checks:
    1. FINFORGE_TEMPLATE_DIR environment variable if set.
    2. Packaged template directory within finforge.templates.component.
    3. Repository root templates/component directory.

    Returns:
        Path to the validated template directory.

    Raises:
        TemplateNotFoundError: If no valid template directory can be found.
    """
    env_dir = os.environ.get("FINFORGE_TEMPLATE_DIR")
    if env_dir:
        path = Path(env_dir).resolve()
        if path.is_dir():
            return path

    # Check packaged directory
    pkg_template = Path(__file__).resolve().parent.parent / "templates" / "component"
    if pkg_template.is_dir():
        return pkg_template

    # Check repo root templates
    repo_template = Path(__file__).resolve().parents[3] / "templates" / "component"
    if repo_template.is_dir():
        return repo_template

    raise TemplateNotFoundError(
        "Default component template directory not found. "
        "Set FINFORGE_TEMPLATE_DIR to specify the location."
    )


def render_template_string(template_str: str, context: dict[str, Any]) -> str:
    """Substitute {{ variable_name }} tokens in a template string with context values.

    Args:
        template_str: Raw template string with {{ token }} placeholders.
        context: Dictionary mapping variable names to their string values.

    Returns:
        Rendered string with all tokens substituted.

    Raises:
        TemplateRenderError: If a token exists in the template but is missing from
            the context dictionary.
    """

    def _replace_token(match: re.Match[str]) -> str:
        var_name = match.group(1)
        if var_name not in context:
            raise TemplateRenderError(
                f"Missing required template variable: '{var_name}'."
            )
        return str(context[var_name])

    return _TOKEN_PATTERN.sub(_replace_token, template_str)


def render_template_path_segment(
    segment: str,
    context: dict[str, Any],
) -> str:
    """Render a path segment (filename or directory name) substituting tokens.

    Args:
        segment: Path segment containing optional {{ token }} placeholders.
        context: Dictionary mapping variable names to replacement values.

    Returns:
        Substituted path segment string.
    """
    return render_template_string(segment, context)
