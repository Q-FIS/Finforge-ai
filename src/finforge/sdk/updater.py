"""Manifest updater engine for FinForge AI components and pipelines.

This module inspects Python source code and synchronizes `component.yaml`
and `pipeline.yaml` manifests automatically, keeping declarative manifests
aligned with implementation changes.
"""

from __future__ import annotations

import ast
import copy
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from finforge.manifest.models import (
    SUPPORTED_CATEGORIES,
    ComponentManifest,
)
from finforge.pipeline.serialization import (
    CURRENT_FORMAT_VERSION,
    PipelineDocument,
    compute_document_execution_order,
)
from finforge.sdk.normalization import normalize_component_name

# -----------------------------------------------------------------------------
# Change Tracking Data Models
# -----------------------------------------------------------------------------


@dataclass
class FieldChange:
    """Represents a specific modification between old and new manifest state."""

    field_name: str
    change_type: str  # "added", "removed", "modified", "synced"
    old_value: Any = None
    new_value: Any = None
    description: str = ""

    def summary(self) -> str:
        """Return a human-readable summary of the change."""
        if self.description:
            return self.description
        if self.change_type == "added":
            return f"+ Added {self.field_name}: {self.new_value!r}"
        if self.change_type == "removed":
            return f"- Removed {self.field_name} (was: {self.old_value!r})"
        return f"~ Modified {self.field_name}: {self.old_value!r} -> {self.new_value!r}"


@dataclass
class ComponentUpdateResult:
    """Outcome of a component manifest update operation."""

    component_name: str
    target_path: Path
    manifest_path: Path
    manifest: ComponentManifest | None = None
    changes: list[FieldChange] = field(default_factory=list)
    is_updated: bool = False
    is_new: bool = False
    error: str | None = None


@dataclass
class PipelineUpdateResult:
    """Outcome of a pipeline manifest update operation."""

    pipeline_name: str
    target_path: Path
    manifest_path: Path
    document: PipelineDocument | None = None
    changes: list[FieldChange] = field(default_factory=list)
    is_updated: bool = False
    is_new: bool = False
    error: str | None = None


# -----------------------------------------------------------------------------
# Component Code Analyzer
# -----------------------------------------------------------------------------


class ComponentCodeAnalyzer:
    """Inspects component Python source files using AST to extract manifest metadata."""

    def __init__(self, target_path: Path) -> None:
        self.target_path = target_path.resolve()
        self.component_dir, self.source_files = self._resolve_files(self.target_path)

    @classmethod
    def _resolve_files(cls, target: Path) -> tuple[Path, list[Path]]:
        """Identify component root directory and relevant Python source files."""
        if target.is_file():
            if target.suffix == ".py":
                # Find enclosing component dir
                parent = target.parent
                if parent.name == "src" or (parent.parent / "src").is_dir():
                    comp_dir = parent.parent
                elif (parent / "component.yaml").is_file():
                    comp_dir = parent
                else:
                    comp_dir = parent
                return comp_dir, [target]
            if target.name == "component.yaml":
                comp_dir = target.parent
                src_dir = comp_dir / "src"
                py_files = (
                    list(src_dir.rglob("*.py"))
                    if src_dir.is_dir()
                    else list(comp_dir.glob("*.py"))
                )
                return comp_dir, py_files

        comp_dir = target
        src_dir = comp_dir / "src"
        if src_dir.is_dir():
            py_files = sorted(src_dir.rglob("*.py"))
        else:
            py_files = sorted(comp_dir.glob("*.py"))

        # Sort so that component.py is analyzed first
        def file_sort_key(p: Path) -> int:
            if p.name == "component.py":
                return 0
            if "__init__" in p.name:
                return 2
            return 1

        py_files.sort(key=file_sort_key)
        return comp_dir, py_files

    def analyze(self) -> dict[str, Any]:
        """Analyze Python files in the component to extract manifest metadata."""
        discovered: dict[str, Any] = {
            "name": None,
            "version": None,
            "description": None,
            "category": "machine-learning",
            "entrypoint": None,
            "inputs": {},
            "outputs": {},
            "config": {},
            "dependencies": [],
        }

        # 1. Inspect pyproject.toml if available
        pyproject_path = self.component_dir / "pyproject.toml"
        if pyproject_path.is_file():
            try:
                pyproj_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
                project_sec = pyproj_data.get("project", {})
                if project_sec.get("name"):
                    raw_name = project_sec["name"]
                    # Clean package name for manifest name if matching folder
                    if (
                        raw_name.startswith("finforge-")
                        and self.component_dir.name != raw_name
                    ):
                        discovered["name"] = raw_name.removeprefix("finforge-")
                    else:
                        discovered["name"] = raw_name
                if project_sec.get("version"):
                    discovered["version"] = str(project_sec["version"])
                if project_sec.get("description"):
                    discovered["description"] = project_sec["description"]
                if project_sec.get("dependencies"):
                    raw_deps = project_sec["dependencies"]
                    clean_deps = [
                        d
                        for d in raw_deps
                        if isinstance(d, str) and not d.startswith("finforge-ai")
                    ]
                    discovered["dependencies"] = clean_deps
            except Exception:
                pass

        # 2. Parse AST of python source files
        for py_file in self.source_files:
            try:
                source_code = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source_code, filename=str(py_file))
            except Exception:
                continue

            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue

                if not self._is_component_class(node):
                    continue

                # Found component class!
                class_name = node.name
                module_path = self._derive_module_path(py_file)
                discovered["entrypoint"] = f"{module_path}:{class_name}"

                # Class docstring
                class_doc = ast.get_docstring(node)
                if class_doc:
                    summary = class_doc.strip().split("\n\n")[0].strip()
                    summary = summary.replace("\n", " ")
                    if summary and not discovered.get("description"):
                        discovered["description"] = summary

                    # Parse structured docstring sections
                    doc_info = self._parse_docstring_sections(class_doc)
                    self._merge_docstring_info(discovered, doc_info)

                # Analyze methods in class
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        if item.name == "setup":
                            self._analyze_setup_method(item, discovered)
                        elif item.name == "run":
                            self._analyze_run_method(item, discovered)

                # Use component name if not yet set
                if not discovered["name"]:
                    slug = re.sub(r"Component$", "", class_name)
                    slug = re.sub(r"(?<!^)(?=[A-Z])", "-", slug).lower()
                    discovered["name"] = slug

                # We found the primary component class, stop searching further classes
                break

        if not discovered["name"]:
            discovered["name"] = normalize_component_name(self.component_dir.name)
        if not discovered["version"]:
            discovered["version"] = "0.1.0"
        if not discovered["description"]:
            discovered["description"] = (
                f"A FinForge AI component for {discovered['name']}."
            )

        return discovered

    def _is_component_class(self, node: ast.ClassDef) -> bool:
        """Determine if an AST ClassDef represents a FinForge BaseComponent."""
        for base in node.bases:
            if isinstance(base, ast.Name) and "Component" in base.id:
                return True
            if isinstance(base, ast.Attribute) and "Component" in base.attr:
                return True

        if node.name.endswith("Component"):
            return True

        method_names = {m.name for m in node.body if isinstance(m, ast.FunctionDef)}
        return {"setup", "run"}.issubset(method_names)

    def _derive_module_path(self, py_file: Path) -> str:
        """Derive python import module path relative to src/ or package root."""
        src_dir = self.component_dir / "src"
        if src_dir.is_dir() and py_file.is_relative_to(src_dir):
            rel = py_file.relative_to(src_dir)
            parts = list(rel.with_suffix("").parts)
            return ".".join(parts)

        rel = py_file.relative_to(self.component_dir)
        parts = list(rel.with_suffix("").parts)
        if parts and parts[0] == "src":
            parts = parts[1:]
        return ".".join(parts)

    def _analyze_setup_method(
        self, method: ast.FunctionDef, discovered: dict[str, Any]
    ) -> None:
        """Extract config schema from setup() method."""
        doc = ast.get_docstring(method)
        if doc:
            doc_info = self._parse_docstring_sections(doc)
            self._merge_docstring_info(discovered, doc_info)

        # Walk AST inside setup
        for node in ast.walk(method):
            # Look for config.get("param", default)
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "get"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "config"
                ) and (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    key = node.args[0].value
                    default_val = None
                    cfg_type = "string"

                    if len(node.args) > 1:
                        default_val = self._eval_ast_literal(node.args[1])
                        cfg_type = self._infer_config_type(default_val)

                    if key not in discovered["config"]:
                        discovered["config"][key] = {
                            "type": cfg_type,
                            "required": False,
                            "default": default_val,
                            "description": f"Configuration parameter '{key}'.",
                        }
                    else:
                        if default_val is not None:
                            discovered["config"][key]["default"] = default_val
                            discovered["config"][key]["type"] = cfg_type

            # Look for config["param"]
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "config"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                key = node.slice.value
                if key not in discovered["config"]:
                    discovered["config"][key] = {
                        "type": "string",
                        "required": True,
                        "default": None,
                        "description": f"Config parameter '{key}'.",
                    }

            # Look for isinstance(..., (int, float, str, bool, list, dict)) checks
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "isinstance":
                    self._inspect_isinstance_check(node, discovered["config"])

    def _analyze_run_method(
        self, method: ast.FunctionDef, discovered: dict[str, Any]
    ) -> None:
        """Extract inputs and outputs from run() method."""
        doc = ast.get_docstring(method)
        if doc:
            doc_info = self._parse_docstring_sections(doc)
            self._merge_docstring_info(discovered, doc_info)

        # 1. Inspect inputs checks and access
        for node in ast.walk(method):
            # Check for: if "port" not in inputs: raise ...
            if isinstance(node, ast.Compare):
                for comp in [node.left] + node.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        for target in [node.left] + node.comparators:
                            if isinstance(target, ast.Name) and target.id == "inputs":
                                port_name = comp.value
                                is_not_in = any(
                                    isinstance(op, ast.NotIn) for op in node.ops
                                )
                                if port_name not in discovered["inputs"]:
                                    discovered["inputs"][port_name] = {
                                        "type": "any",
                                        "required": is_not_in,
                                        "description": f"Input port '{port_name}'.",
                                    }
                                elif is_not_in:
                                    discovered["inputs"][port_name]["required"] = True

            # Check for: raw_data = inputs["port"] or inputs["port"]
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "inputs"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                port_name = node.slice.value
                if port_name not in discovered["inputs"]:
                    discovered["inputs"][port_name] = {
                        "type": "any",
                        "required": True,
                        "description": f"Input port '{port_name}'.",
                    }

            # Check for: inputs.get("port")
            elif isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "get"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "inputs"
                ) and (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    port_name = node.args[0].value
                    if port_name not in discovered["inputs"]:
                        discovered["inputs"][port_name] = {
                            "type": "any",
                            "required": False,
                            "description": f"Optional input port '{port_name}'.",
                        }
                    else:
                        discovered["inputs"][port_name]["required"] = False

            # Check for: isinstance(..., list/str/float/int/bool/dict)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "isinstance":
                    self._inspect_isinstance_check(node, discovered["inputs"])

        # 2. Inspect returns for outputs
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Return)
                and node.value is not None
                and isinstance(node.value, ast.Dict)
            ):
                for k, v in zip(node.value.keys, node.value.values, strict=False):
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            out_name = k.value
                            out_type = self._infer_output_type(v)
                            if out_name not in discovered["outputs"]:
                                discovered["outputs"][out_name] = {
                                    "type": out_type,
                                    "description": f"Output port '{out_name}'.",
                                }
                            else:
                                if (
                                    discovered["outputs"][out_name]["type"]
                                    in ("any", "string")
                                    and out_type != "any"
                                ):
                                    discovered["outputs"][out_name]["type"] = out_type

    def _inspect_isinstance_check(
        self, call_node: ast.Call, target_dict: dict[str, Any]
    ) -> None:
        """Inspect an isinstance() call to infer types for variables/keys."""
        if len(call_node.args) < 2:
            return

        arg0 = call_node.args[0]
        arg1 = call_node.args[1]

        target_name: str | None = None
        if isinstance(arg0, ast.Subscript):
            if isinstance(arg0.slice, ast.Constant) and isinstance(
                arg0.slice.value, str
            ):
                target_name = arg0.slice.value
        elif isinstance(arg0, ast.Name):
            for k in target_dict:
                if (
                    k == arg0.id
                    or k.replace("_", "") == arg0.id.replace("_", "")
                    or arg0.id.endswith(k)
                ):
                    target_name = k
                    break

        if not target_name or target_name not in target_dict:
            return

        type_names: list[str] = []
        if isinstance(arg1, ast.Name):
            type_names.append(arg1.id)
        elif isinstance(arg1, ast.Tuple):
            for elt in arg1.elts:
                if isinstance(elt, ast.Name):
                    type_names.append(elt.id)

        inferred = self._map_python_types_to_manifest_type(type_names)
        if inferred:
            target_dict[target_name]["type"] = inferred

    @staticmethod
    def _map_python_types_to_manifest_type(py_types: list[str]) -> str | None:
        """Map Python type names from isinstance checks to manifest port types."""
        types_set = set(py_types)
        if "list" in types_set:
            return "array"
        if "str" in types_set:
            return "string"
        if "bool" in types_set and len(types_set) == 1:
            return "boolean"
        if "float" in types_set:
            return "float"
        if "int" in types_set:
            return "integer"
        if "dict" in types_set:
            return "object"
        if "DataFrame" in types_set:
            return "dataframe"
        if "Tensor" in types_set:
            return "tensor"
        return None

    @staticmethod
    def _infer_config_type(val: Any) -> str:
        """Infer FinForge config type string from Python literal value."""
        if isinstance(val, bool):
            return "boolean"
        if isinstance(val, int):
            return "integer"
        if isinstance(val, float):
            return "float"
        if isinstance(val, str):
            return "string"
        if isinstance(val, list):
            return "list"
        if isinstance(val, dict):
            return "dict"
        return "string"

    @staticmethod
    def _infer_output_type(val_node: ast.AST) -> str:
        """Infer output port type from AST node."""
        if isinstance(val_node, (ast.List, ast.ListComp)):
            return "array"
        if isinstance(val_node, ast.Constant):
            if isinstance(val_node.value, str):
                return "string"
            if isinstance(val_node.value, bool):
                return "boolean"
            if isinstance(val_node.value, int):
                return "integer"
            if isinstance(val_node.value, float):
                return "float"
        if isinstance(val_node, ast.Dict):
            return "object"
        if isinstance(val_node, ast.Call):
            func = val_node.func
            if isinstance(func, ast.Name):
                if func.id in ("list", "sorted"):
                    return "array"
                if func.id == "str":
                    return "string"
                if func.id == "float":
                    return "float"
                if func.id == "int":
                    return "integer"
                if func.id == "bool":
                    return "boolean"
                if func.id == "dict":
                    return "object"
        return "any"

    @staticmethod
    def _eval_ast_literal(node: ast.AST) -> Any:
        """Safely evaluate AST node to Python literal."""
        try:
            return ast.literal_eval(node)
        except Exception:
            return None

    @staticmethod
    def _parse_docstring_sections(doc: str) -> dict[str, dict[str, dict[str, Any]]]:
        """Parse structured docstrings to extract port/config descriptions and types."""
        result: dict[str, dict[str, dict[str, Any]]] = {
            "inputs": {},
            "outputs": {},
            "config": {},
        }
        current_section: str | None = None

        section_headers = {
            "inputs": "inputs",
            "input ports": "inputs",
            "outputs": "outputs",
            "output ports": "outputs",
            "config": "config",
            "configuration": "config",
        }

        item_pattern = re.compile(
            r"^\s*([a-zA-Z0-9_]+)(?:\s*\(([a-zA-Z0-9_]+)\))?\s*:\s*(.+)$"
        )

        for line in doc.splitlines():
            clean = line.strip()
            lower = clean.lower().rstrip(":")
            if lower in section_headers:
                current_section = section_headers[lower]
                continue
            if clean.startswith("Args:") or clean.startswith("Returns:"):
                current_section = None
                continue

            if current_section and clean:
                match = item_pattern.match(line)
                if match:
                    name, type_str, desc = match.groups()
                    entry: dict[str, Any] = {"description": desc.strip()}
                    if type_str:
                        norm_type = type_str.lower().strip()
                        if norm_type in ("str", "string"):
                            entry["type"] = "string"
                        elif norm_type in ("int", "integer"):
                            entry["type"] = "integer"
                        elif norm_type in ("float", "number"):
                            entry["type"] = "float"
                        elif norm_type in ("bool", "boolean"):
                            entry["type"] = "boolean"
                        elif norm_type in ("list", "array"):
                            entry["type"] = "array"
                        elif norm_type in ("dict", "object"):
                            entry["type"] = "object"
                    result[current_section][name] = entry

        return result

    @staticmethod
    def _merge_docstring_info(
        discovered: dict[str, Any],
        doc_info: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        """Merge docstring information into discovered manifest data."""
        for sec in ("inputs", "outputs", "config"):
            for name, meta in doc_info[sec].items():
                if name not in discovered[sec]:
                    discovered[sec][name] = {
                        "type": meta.get(
                            "type", "any" if sec != "config" else "string"
                        ),
                        "description": meta.get(
                            "description", f"{sec.capitalize()} {name}."
                        ),
                    }
                    if sec == "inputs":
                        is_opt = "optional" in meta.get("description", "").lower()
                        discovered[sec][name]["required"] = not is_opt
                    elif sec == "config":
                        discovered[sec][name]["required"] = False
                        discovered[sec][name]["default"] = None
                else:
                    if meta.get("description"):
                        discovered[sec][name]["description"] = meta["description"]
                    if meta.get("type") and discovered[sec][name].get("type") in (
                        "any",
                        "string",
                    ):
                        discovered[sec][name]["type"] = meta["type"]


# -----------------------------------------------------------------------------
# Component Manifest Comparison & Updater
# -----------------------------------------------------------------------------


def _manifests_semantically_equal(
    old_data: dict[str, Any],
    new_data: dict[str, Any],
) -> bool:
    """Evaluate whether two manifest dictionaries are semantically identical."""
    for fld in ("name", "version", "description", "category", "entrypoint"):
        if str(old_data.get(fld, "")).strip() != str(new_data.get(fld, "")).strip():
            return False

    # Check dependencies
    old_deps = sorted(str(d).strip() for d in (old_data.get("dependencies") or []))
    new_deps = sorted(str(d).strip() for d in (new_data.get("dependencies") or []))
    if old_deps != new_deps:
        return False

    def _items_equal(oi: Any, ni: Any) -> bool:
        if oi is None and ni is None:
            return True
        if oi is None or ni is None:
            return False
        if not isinstance(oi, dict) or not isinstance(ni, dict):
            return bool(oi == ni)
        if oi.get("type") != ni.get("type"):
            return False
        return bool(_items_equal(oi.get("items"), ni.get("items")))

    # Check inputs
    old_inputs = old_data.get("inputs", {})
    new_inputs = new_data.get("inputs", {})
    if set(old_inputs.keys()) != set(new_inputs.keys()):
        return False
    for k in old_inputs:
        oi, ni = old_inputs[k], new_inputs[k]
        if oi.get("type") != ni.get("type"):
            return False
        if oi.get("required", True) != ni.get("required", True):
            return False
        if not _items_equal(oi.get("items"), ni.get("items")):
            return False

    # Check outputs
    old_outputs = old_data.get("outputs", {})
    new_outputs = new_data.get("outputs", {})
    if set(old_outputs.keys()) != set(new_outputs.keys()):
        return False
    for k in old_outputs:
        oo, no = old_outputs[k], new_outputs[k]
        if oo.get("type") != no.get("type"):
            return False
        if not _items_equal(oo.get("items"), no.get("items")):
            return False

    # Check config
    old_cfg = old_data.get("config", {})
    new_cfg = new_data.get("config", {})
    if set(old_cfg.keys()) != set(new_cfg.keys()):
        return False
    for k in old_cfg:
        oc, nc = old_cfg[k], new_cfg[k]
        if oc.get("type") != nc.get("type"):
            return False
        if oc.get("default") != nc.get("default"):
            return False
        if oc.get("required", False) != nc.get("required", False):
            return False

    return True


def update_component(
    path: str | Path = ".",
    *,
    dry_run: bool = False,
    check: bool = False,
) -> ComponentUpdateResult:
    """Analyze component code and update its `component.yaml` manifest.

    Args:
        path: Path to component directory, `component.yaml`, or python file.
        dry_run: If True, do not write modifications to disk.
        check: If True, only check if manifest matches code without writing.

    Returns:
        `ComponentUpdateResult` containing discovered manifest, list of changes,
        and update status.
    """
    target = Path(path).resolve()
    analyzer = ComponentCodeAnalyzer(target)
    comp_dir = analyzer.component_dir
    manifest_path = comp_dir / "component.yaml"

    if not analyzer.source_files:
        return ComponentUpdateResult(
            component_name=comp_dir.name,
            target_path=comp_dir,
            manifest_path=manifest_path,
            error=f"No Python source files found in '{comp_dir}'.",
        )

    code_meta = analyzer.analyze()

    existing_manifest: dict[str, Any] = {}
    is_new = not manifest_path.is_file()
    if not is_new:
        try:
            content = manifest_path.read_text(encoding="utf-8")
            loaded = yaml.safe_load(content)
            if isinstance(loaded, dict):
                existing_manifest = loaded
        except Exception as exc:
            return ComponentUpdateResult(
                component_name=comp_dir.name,
                target_path=comp_dir,
                manifest_path=manifest_path,
                error=f"Failed to read existing manifest '{manifest_path}': {exc}",
            )

    # Preserve existing name if already valid, otherwise use discovered name
    comp_name = (
        existing_manifest.get("name")
        or code_meta["name"]
        or normalize_component_name(comp_dir.name)
    )

    changes: list[FieldChange] = []

    # Assemble updated manifest dictionary, merging code metadata with existing
    updated_dict: dict[str, Any] = {
        "name": comp_name,
        "version": existing_manifest.get("version", code_meta.get("version", "0.1.0")),
        "description": existing_manifest.get("description")
        or code_meta.get("description")
        or f"FinForge AI {comp_name} component.",
        "api_version": existing_manifest.get("api_version", "1"),
        "category": existing_manifest.get(
            "category", code_meta.get("category", "machine-learning")
        ),
        "entrypoint": code_meta.get("entrypoint")
        or existing_manifest.get("entrypoint"),
        "inputs": {},
        "outputs": {},
        "config": {},
        "dependencies": existing_manifest.get(
            "dependencies", code_meta.get("dependencies", [])
        ),
    }

    if not updated_dict["entrypoint"]:
        return ComponentUpdateResult(
            component_name=comp_name,
            target_path=comp_dir,
            manifest_path=manifest_path,
            error=f"Could not determine component class entrypoint in '{comp_dir}'.",
        )

    if updated_dict["category"] not in SUPPORTED_CATEGORIES:
        updated_dict["category"] = "machine-learning"

    # Merge Inputs
    existing_inputs = existing_manifest.get("inputs", {})
    code_inputs = code_meta.get("inputs", {})
    all_input_keys = list(
        dict.fromkeys(list(existing_inputs.keys()) + list(code_inputs.keys()))
    )

    for k in all_input_keys:
        if k in code_inputs and k in existing_inputs:
            ex = copy.deepcopy(existing_inputs[k])
            cd = code_inputs[k]
            new_type = ex.get("type", cd.get("type", "any"))
            if new_type == "any" and cd.get("type") != "any":
                new_type = cd.get("type")
            merged_port: dict[str, Any] = {
                "type": new_type,
                "required": cd.get("required", ex.get("required", True)),
                "description": ex.get("description")
                or cd.get("description", f"Input port '{k}'."),
            }
            if "items" in ex and merged_port["type"] == "array":
                merged_port["items"] = ex["items"]
            updated_dict["inputs"][k] = merged_port
        elif k in code_inputs:
            cd = code_inputs[k]
            updated_dict["inputs"][k] = {
                "type": cd.get("type", "any"),
                "required": cd.get("required", True),
                "description": cd.get("description", f"Input port '{k}'."),
            }
            p_type = updated_dict["inputs"][k]["type"]
            changes.append(
                FieldChange(
                    field_name=f"inputs.{k}",
                    change_type="added",
                    new_value=updated_dict["inputs"][k],
                    description=f"+ Added input port '{k}' (type: {p_type})",
                )
            )
        else:
            updated_dict["inputs"][k] = existing_inputs[k]

    # Merge Outputs
    existing_outputs = existing_manifest.get("outputs", {})
    code_outputs = code_meta.get("outputs", {})
    all_output_keys = list(
        dict.fromkeys(list(existing_outputs.keys()) + list(code_outputs.keys()))
    )

    for k in all_output_keys:
        if k in code_outputs and k in existing_outputs:
            ex = copy.deepcopy(existing_outputs[k])
            cd = code_outputs[k]
            new_type = ex.get("type", cd.get("type", "any"))
            if new_type in ("any", "string") and cd.get("type") not in (
                "any",
                "string",
            ):
                new_type = cd.get("type")
            merged_out: dict[str, Any] = {
                "type": new_type,
                "description": ex.get("description")
                or cd.get("description", f"Output port '{k}'."),
            }
            if "items" in ex and merged_out["type"] == "array":
                merged_out["items"] = ex["items"]
            updated_dict["outputs"][k] = merged_out
        elif k in code_outputs:
            cd = code_outputs[k]
            updated_dict["outputs"][k] = {
                "type": cd.get("type", "any"),
                "description": cd.get("description", f"Output port '{k}'."),
            }
            o_type = updated_dict["outputs"][k]["type"]
            changes.append(
                FieldChange(
                    field_name=f"outputs.{k}",
                    change_type="added",
                    new_value=updated_dict["outputs"][k],
                    description=f"+ Added output port '{k}' (type: {o_type})",
                )
            )
        else:
            updated_dict["outputs"][k] = existing_outputs[k]

    # Merge Config
    existing_config = existing_manifest.get("config", {})
    code_config = code_meta.get("config", {})
    all_config_keys = list(
        dict.fromkeys(list(existing_config.keys()) + list(code_config.keys()))
    )

    for k in all_config_keys:
        if k in code_config and k in existing_config:
            ex = copy.deepcopy(existing_config[k])
            cd = code_config[k]
            merged_cfg: dict[str, Any] = {
                "type": cd.get("type", ex.get("type", "string")),
                "required": cd.get("required", ex.get("required", False)),
                "default": cd.get("default", ex.get("default")),
                "description": ex.get("description")
                or cd.get("description", f"Config '{k}'."),
            }
            # Only record change if type, default, or required changed semantically
            type_changed = ex.get("type") != merged_cfg.get("type")
            default_changed = ex.get("default") != merged_cfg.get("default")
            req_changed = ex.get("required", False) != merged_cfg.get("required", False)
            if type_changed or default_changed or req_changed:
                cfg_def = merged_cfg["default"]
                changes.append(
                    FieldChange(
                        field_name=f"config.{k}",
                        change_type="modified",
                        old_value=ex,
                        new_value=merged_cfg,
                        description=f"~ Updated config '{k}': default={cfg_def!r}",
                    )
                )
            updated_dict["config"][k] = merged_cfg
        elif k in code_config:
            cd = code_config[k]
            updated_dict["config"][k] = {
                "type": cd.get("type", "string"),
                "required": cd.get("required", False),
                "default": cd.get("default"),
                "description": cd.get("description", f"Config '{k}'."),
            }
            def_val = cd.get("default")
            changes.append(
                FieldChange(
                    field_name=f"config.{k}",
                    change_type="added",
                    new_value=updated_dict["config"][k],
                    description=f"+ Added config '{k}' (default: {def_val!r})",
                )
            )
        else:
            updated_dict["config"][k] = existing_config[k]

    # Track metadata changes
    for fld in ("entrypoint", "version", "description"):
        old_val = existing_manifest.get(fld)
        new_val = updated_dict.get(fld)
        if old_val != new_val and old_val is not None:
            changes.append(
                FieldChange(
                    field_name=fld,
                    change_type="modified",
                    old_value=old_val,
                    new_value=new_val,
                    description=f"~ Updated {fld}: {old_val!r} -> {new_val!r}",
                )
            )

    # Validate against ComponentManifest Pydantic model
    try:
        validated_manifest = ComponentManifest.model_validate(updated_dict)
    except Exception as exc:
        return ComponentUpdateResult(
            component_name=comp_name,
            target_path=comp_dir,
            manifest_path=manifest_path,
            error=f"Component validation failed: {exc}",
        )

    # Format new YAML content
    new_yaml = _format_component_yaml(validated_manifest)

    # Check whether file has actually changed semantically
    is_equal = not is_new and _manifests_semantically_equal(
        existing_manifest, updated_dict
    )
    has_diff = is_new or (not is_equal)

    if is_new:
        changes.append(
            FieldChange(
                field_name="manifest",
                change_type="added",
                new_value=manifest_path.name,
                description=f"+ Created new manifest: {manifest_path.name}",
            )
        )

    if has_diff and not dry_run and not check:
        temp_file = manifest_path.parent / f".{manifest_path.name}.tmp"
        temp_file.write_text(new_yaml, encoding="utf-8")
        temp_file.replace(manifest_path)

    return ComponentUpdateResult(
        component_name=comp_name,
        target_path=comp_dir,
        manifest_path=manifest_path,
        manifest=validated_manifest,
        changes=changes,
        is_updated=has_diff,
        is_new=is_new,
    )


def _format_component_yaml(manifest: ComponentManifest) -> str:
    """Format a ComponentManifest object as clean, human-readable YAML."""
    manifest_dict = manifest.model_dump(exclude_none=True)
    key_order = [
        "name",
        "version",
        "description",
        "api_version",
        "category",
        "entrypoint",
        "inputs",
        "outputs",
        "config",
        "dependencies",
    ]
    ordered_dict: dict[str, Any] = {}
    for k in key_order:
        if k in manifest_dict:
            ordered_dict[k] = manifest_dict[k]
    for k, v in manifest_dict.items():
        if k not in ordered_dict:
            ordered_dict[k] = v

    return yaml.safe_dump(ordered_dict, sort_keys=False, default_flow_style=False)


# -----------------------------------------------------------------------------
# Pipeline Code Analyzer
# -----------------------------------------------------------------------------


class PipelineCodeAnalyzer:
    """Inspects pipeline Python code to extract pipeline topology."""

    def __init__(self, target_path: Path) -> None:
        self.target_path = target_path.resolve()
        self.pipeline_dir, self.py_files = self._resolve_files(self.target_path)

    @classmethod
    def _resolve_files(cls, target: Path) -> tuple[Path, list[Path]]:
        """Identify the pipeline root directory and all relevant Python source files."""
        if target.is_file():
            if target.name == "pipeline.yaml":
                pipe_dir = target.parent
                return pipe_dir, sorted(pipe_dir.glob("*.py"))
            pipe_dir = target.parent
            return pipe_dir, [target]

        pipe_dir = target
        py_files = sorted(pipe_dir.glob("*.py"))
        return pipe_dir, py_files

    def analyze(self) -> dict[str, Any]:
        """Analyze Python files in the pipeline to extract Pipeline graph topology."""
        doc_data: dict[str, Any] = {
            "format_version": CURRENT_FORMAT_VERSION,
            "name": None,
            "description": None,
            "metadata": {},
            "nodes": [],
            "edges": [],
        }

        # 1. Inspect Python files for Pipeline builder calls
        for py_file in self.py_files:
            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_file))
            except Exception:
                continue

            extracted = self._extract_pipeline_from_ast(tree)
            if extracted.get("name") or extracted.get("nodes"):
                if extracted.get("name"):
                    doc_data["name"] = extracted["name"]
                if extracted.get("description"):
                    doc_data["description"] = extracted["description"]
                if extracted.get("metadata"):
                    doc_data["metadata"].update(extracted["metadata"])
                if extracted.get("nodes"):
                    doc_data["nodes"] = extracted["nodes"]
                if extracted.get("edges"):
                    doc_data["edges"] = extracted["edges"]
                break

        # 2. Inspect local components directory
        comps_dir = self.pipeline_dir / "components"
        if comps_dir.is_dir():
            local_nodes = self._discover_local_components(comps_dir)
            existing_node_ids = {n["id"] for n in doc_data["nodes"]}
            existing_comp_names = {n["component"] for n in doc_data["nodes"]}

            for comp_node in local_nodes:
                if (
                    comp_node["component"] not in existing_comp_names
                    and comp_node["id"] not in existing_node_ids
                ):
                    doc_data["nodes"].append(comp_node)

        if not doc_data["name"]:
            doc_data["name"] = normalize_component_name(self.pipeline_dir.name)

        return doc_data

    @classmethod
    def _extract_pipeline_from_ast(cls, tree: ast.AST) -> dict[str, Any]:
        """Extract pipeline nodes and edges from AST calls to Pipeline builder API."""
        extracted: dict[str, Any] = {
            "name": None,
            "description": None,
            "metadata": {},
            "nodes": [],
            "edges": [],
        }

        def eval_literal(node: ast.AST | None) -> Any:
            if node is None:
                return None
            try:
                return ast.literal_eval(node)
            except Exception:
                return None

        pipeline_var_names: set[str] = set()

        for stmt in ast.walk(tree):
            if isinstance(stmt, ast.Assign):
                if isinstance(stmt.value, ast.Call):
                    func_name = getattr(stmt.value.func, "id", None) or getattr(
                        stmt.value.func, "attr", None
                    )
                    if func_name == "Pipeline":
                        for target in stmt.targets:
                            if isinstance(target, ast.Name):
                                pipeline_var_names.add(target.id)

                        for kw in stmt.value.keywords:
                            if kw.arg == "name":
                                extracted["name"] = eval_literal(kw.value)
                            elif kw.arg == "description":
                                extracted["description"] = eval_literal(kw.value)
                            elif kw.arg == "metadata":
                                extracted["metadata"] = eval_literal(kw.value) or {}

                        if stmt.value.args and not extracted["name"]:
                            extracted["name"] = eval_literal(stmt.value.args[0])

            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                if isinstance(call.func, ast.Attribute):
                    var_name = getattr(call.func.value, "id", None)
                    is_pipeline_call = (
                        var_name in pipeline_var_names
                        or var_name in ("p", "pipeline", "builder")
                        or not pipeline_var_names
                    )

                    if is_pipeline_call and call.func.attr == "add":
                        args = [eval_literal(a) for a in call.args]
                        kws = {kw.arg: eval_literal(kw.value) for kw in call.keywords}
                        node_id = args[0] if len(args) > 0 else kws.get("node_id")
                        comp_name = (
                            args[1] if len(args) > 1 else kws.get("component_name")
                        )
                        cfg = (args[2] if len(args) > 2 else kws.get("config")) or {}
                        meta = (args[3] if len(args) > 3 else kws.get("metadata")) or {}
                        if node_id and comp_name:
                            extracted["nodes"].append(
                                {
                                    "id": str(node_id),
                                    "component": str(comp_name),
                                    "config": cfg if isinstance(cfg, dict) else {},
                                    "metadata": meta if isinstance(meta, dict) else {},
                                }
                            )

                    elif is_pipeline_call and call.func.attr == "connect":
                        args = [eval_literal(a) for a in call.args]
                        kws = {kw.arg: eval_literal(kw.value) for kw in call.keywords}
                        src_n = args[0] if len(args) > 0 else kws.get("source_node")
                        src_p = args[1] if len(args) > 1 else kws.get("source_port")
                        dst_n = (
                            args[2] if len(args) > 2 else kws.get("destination_node")
                        )
                        dst_p = (
                            args[3] if len(args) > 3 else kws.get("destination_port")
                        )
                        if src_n and src_p and dst_n and dst_p:
                            extracted["edges"].append(
                                {
                                    "source_node": str(src_n),
                                    "source_port": str(src_p),
                                    "destination_node": str(dst_n),
                                    "destination_port": str(dst_p),
                                }
                            )

        return extracted

    @classmethod
    def _discover_local_components(cls, comps_dir: Path) -> list[dict[str, Any]]:
        """Discover components scaffolded in local components directory."""
        from finforge.manifest import load_manifest

        nodes: list[dict[str, Any]] = []
        for yaml_path in sorted(comps_dir.glob("*/component.yaml")):
            try:
                manifest = load_manifest(yaml_path)
                default_cfg: dict[str, Any] = {}
                for k, cfg_def in manifest.config.items():
                    if cfg_def.default is not None:
                        default_cfg[k] = cfg_def.default

                nodes.append(
                    {
                        "id": manifest.name.replace("-", "_"),
                        "component": manifest.name,
                        "config": default_cfg,
                        "metadata": {},
                    }
                )
            except Exception:
                continue
        return nodes


# -----------------------------------------------------------------------------
# Pipeline Manifest Comparison & Updater
# -----------------------------------------------------------------------------


def _pipeline_docs_semantically_equal(
    old_doc: dict[str, Any],
    new_doc: dict[str, Any],
) -> bool:
    """Evaluate whether two pipeline documents are semantically identical."""
    if str(old_doc.get("name", "")).strip() != str(new_doc.get("name", "")).strip():
        return False
    if (
        str(old_doc.get("description", "")).strip()
        != str(new_doc.get("description", "")).strip()
    ):
        return False
    if old_doc.get("metadata", {}) != new_doc.get("metadata", {}):
        return False

    # Compare nodes
    old_nodes = {
        n["id"]: n
        for n in old_doc.get("nodes", [])
        if isinstance(n, dict) and "id" in n
    }
    new_nodes = {
        n["id"]: n
        for n in new_doc.get("nodes", [])
        if isinstance(n, dict) and "id" in n
    }
    if set(old_nodes.keys()) != set(new_nodes.keys()):
        return False
    for nid in old_nodes:
        on, nn = old_nodes[nid], new_nodes[nid]
        if on.get("component") != nn.get("component"):
            return False
        if on.get("config", {}) != nn.get("config", {}):
            return False

    # Compare edges
    def edge_key(e: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            e.get("source_node", ""),
            e.get("source_port", ""),
            e.get("destination_node", ""),
            e.get("destination_port", ""),
        )

    old_edges = sorted(
        edge_key(e) for e in old_doc.get("edges", []) if isinstance(e, dict)
    )
    new_edges = sorted(
        edge_key(e) for e in new_doc.get("edges", []) if isinstance(e, dict)
    )
    return old_edges == new_edges


def update_pipeline(
    path: str | Path = ".",
    *,
    dry_run: bool = False,
    check: bool = False,
) -> PipelineUpdateResult:
    """Analyze pipeline code and local components to update `pipeline.yaml`.

    Args:
        path: Path to pipeline directory, `pipeline.yaml`, or python file.
        dry_run: If True, do not write modifications to disk.
        check: If True, only check if manifest matches code without writing.

    Returns:
        `PipelineUpdateResult` containing discovered document, list of changes,
        and update status.
    """
    target = Path(path).resolve()
    analyzer = PipelineCodeAnalyzer(target)
    pipe_dir = analyzer.pipeline_dir
    manifest_path = pipe_dir / "pipeline.yaml"

    code_meta = analyzer.analyze()
    pipe_name = code_meta["name"] or normalize_component_name(pipe_dir.name)

    existing_doc: dict[str, Any] = {}
    is_new = not manifest_path.is_file()
    if not is_new:
        try:
            content = manifest_path.read_text(encoding="utf-8")
            loaded = yaml.safe_load(content)
            if isinstance(loaded, dict):
                existing_doc = loaded
        except Exception as exc:
            return PipelineUpdateResult(
                pipeline_name=pipe_name,
                target_path=pipe_dir,
                manifest_path=manifest_path,
                error=f"Failed to read existing pipeline YAML '{manifest_path}': {exc}",
            )

    changes: list[FieldChange] = []

    # Prepare updated document dictionary
    updated_dict: dict[str, Any] = {
        "format_version": CURRENT_FORMAT_VERSION,
        "name": existing_doc.get("name") or pipe_name,
        "description": code_meta.get("description")
        or existing_doc.get("description", f"Pipeline workflow for {pipe_name}."),
        "metadata": existing_doc.get("metadata", code_meta.get("metadata", {})),
        "nodes": [],
        "edges": [],
    }

    # 1. Merge Nodes
    existing_nodes = {
        n["id"]: n
        for n in existing_doc.get("nodes", [])
        if isinstance(n, dict) and "id" in n
    }
    code_nodes = {n["id"]: n for n in code_meta.get("nodes", [])}

    existing_comps = {n.get("component") for n in existing_nodes.values()}

    # Discover component default configs to sync if local components are present
    comp_default_configs: dict[str, dict[str, Any]] = {}
    comps_dir = pipe_dir / "components"
    if comps_dir.is_dir():
        for comp_yaml in comps_dir.glob("*/component.yaml"):
            try:
                from finforge.manifest import load_manifest

                m = load_manifest(comp_yaml)
                comp_default_configs[m.name] = {
                    k: cfg.default
                    for k, cfg in m.config.items()
                    if cfg.default is not None
                }
            except Exception:
                pass

    all_node_ids = list(
        dict.fromkeys(list(existing_nodes.keys()) + list(code_nodes.keys()))
    )

    for nid in all_node_ids:
        if nid in existing_nodes and nid in code_nodes:
            n = copy.deepcopy(existing_nodes[nid])
            for k, v in code_nodes[nid].get("config", {}).items():
                if k not in n["config"]:
                    n["config"][k] = v
            comp_name = n.get("component")
            if comp_name in comp_default_configs:
                for k, v in comp_default_configs[comp_name].items():
                    if k not in n["config"]:
                        n["config"][k] = v
            updated_dict["nodes"].append(n)
        elif nid in existing_nodes:
            updated_dict["nodes"].append(existing_nodes[nid])
        elif nid in code_nodes:
            n = copy.deepcopy(code_nodes[nid])
            comp_name = n.get("component")
            # If the component is already used in an existing node, skip duplicate
            if comp_name in existing_comps:
                continue
            if comp_name in comp_default_configs:
                for k, v in comp_default_configs[comp_name].items():
                    if k not in n["config"]:
                        n["config"][k] = v
            updated_dict["nodes"].append(n)
            node_comp = n["component"]
            changes.append(
                FieldChange(
                    field_name=f"nodes.{nid}",
                    change_type="added",
                    new_value=n,
                    description=f"+ Added node '{nid}' (comp: {node_comp})",
                )
            )

    # 2. Merge Edges
    if code_meta.get("edges"):
        updated_dict["edges"] = code_meta["edges"]
        if existing_doc.get("edges") != code_meta["edges"]:
            edge_count = len(code_meta["edges"])
            changes.append(
                FieldChange(
                    field_name="edges",
                    change_type="modified",
                    old_value=existing_doc.get("edges"),
                    new_value=code_meta["edges"],
                    description=f"~ Synchronized {edge_count} connections from code",
                )
            )
    else:
        updated_dict["edges"] = existing_doc.get("edges", [])

    # Validate against PipelineDocument
    try:
        validated_doc = PipelineDocument.model_validate(updated_dict)
        compute_document_execution_order(validated_doc)
    except Exception as exc:
        return PipelineUpdateResult(
            pipeline_name=pipe_name,
            target_path=pipe_dir,
            manifest_path=manifest_path,
            error=f"Pipeline validation failed: {exc}",
        )

    # Check whether file has actually changed semantically
    is_equal = not is_new and _pipeline_docs_semantically_equal(
        existing_doc, updated_dict
    )
    has_diff = is_new or (not is_equal)

    if is_new:
        changes.append(
            FieldChange(
                field_name="manifest",
                change_type="added",
                new_value=manifest_path.name,
                description=f"+ Created new pipeline manifest: {manifest_path.name}",
            )
        )

    if has_diff and not dry_run and not check:
        doc_dict = validated_doc.model_dump(exclude_none=True)
        key_order = [
            "format_version",
            "name",
            "description",
            "metadata",
            "nodes",
            "edges",
        ]
        ordered_doc: dict[str, Any] = {}
        for k in key_order:
            if k in doc_dict:
                ordered_doc[k] = doc_dict[k]
        for k, v in doc_dict.items():
            if k not in ordered_doc:
                ordered_doc[k] = v

        yaml_content = yaml.safe_dump(
            ordered_doc, sort_keys=False, default_flow_style=False
        )
        temp_file = manifest_path.parent / f".{manifest_path.name}.tmp"
        temp_file.write_text(yaml_content, encoding="utf-8")
        temp_file.replace(manifest_path)

    return PipelineUpdateResult(
        pipeline_name=pipe_name,
        target_path=pipe_dir,
        manifest_path=manifest_path,
        document=validated_doc,
        changes=changes,
        is_updated=has_diff,
        is_new=is_new,
    )


# -----------------------------------------------------------------------------
# Batch and Auto-Detection Update Engine
# -----------------------------------------------------------------------------


def auto_update(
    target_path: str | Path = ".",
    *,
    force_component: bool = False,
    force_pipeline: bool = False,
    recursive: bool = False,
    dry_run: bool = False,
    check: bool = False,
) -> tuple[list[ComponentUpdateResult], list[PipelineUpdateResult]]:
    """Automatically detect whether target is a component, pipeline, or workspace.

    Args:
        target_path: Target directory or file.
        force_component: Force treat target as a component.
        force_pipeline: Force treat target as a pipeline.
        recursive: Recursively search and update all components and pipelines.
        dry_run: Simulate without writing changes to disk.
        check: Verify manifests match code without writing changes.

    Returns:
        Tuple of (component_results, pipeline_results).
    """
    target = Path(target_path).resolve()
    comp_results: list[ComponentUpdateResult] = []
    pipe_results: list[PipelineUpdateResult] = []

    if force_component:
        c_res = update_component(target, dry_run=dry_run, check=check)
        comp_results.append(c_res)
        return comp_results, pipe_results

    if force_pipeline:
        p_res = update_pipeline(target, dry_run=dry_run, check=check)
        pipe_results.append(p_res)
        return comp_results, pipe_results

    # 1. Single file check
    if target.is_file():
        if target.name == "component.yaml" or (
            target.suffix == ".py" and "component" in target.name
        ):
            comp_results.append(update_component(target, dry_run=dry_run, check=check))
            return comp_results, pipe_results
        if target.name == "pipeline.yaml" or (
            target.suffix == ".py" and "pipeline" in target.name
        ):
            pipe_results.append(update_pipeline(target, dry_run=dry_run, check=check))
            return comp_results, pipe_results

    # 2. Workspace check: if target contains components/ or pipelines/
    is_workspace = (
        recursive or (target / "components").is_dir() or (target / "pipelines").is_dir()
    )

    # Directory check: Is it a single component directory?
    is_comp_dir = (
        not is_workspace
        and (
            (target / "component.yaml").is_file()
            or (target / "src").is_dir()
            or any(target.glob("*component*.py"))
        )
        and not (target / "pipeline.yaml").is_file()
    )

    # Is it a single pipeline directory?
    is_pipe_dir = (
        not is_workspace
        and ((target / "pipeline.yaml").is_file() or any(target.glob("*pipeline*.py")))
        and not (target / "src").is_dir()
    )

    if not recursive and is_comp_dir:
        comp_results.append(update_component(target, dry_run=dry_run, check=check))
        return comp_results, pipe_results

    if not recursive and is_pipe_dir:
        local_comps = target / "components"
        if local_comps.is_dir():
            for c_yaml in sorted(local_comps.glob("*/component.yaml")):
                comp_results.append(
                    update_component(c_yaml.parent, dry_run=dry_run, check=check)
                )
        pipe_results.append(update_pipeline(target, dry_run=dry_run, check=check))
        return comp_results, pipe_results

    # 3. Workspace / recursive scan: discover all components and pipelines
    seen_comps: set[Path] = set()
    for c_yaml in sorted(target.rglob("component.yaml")):
        if any(
            part in (".venv", ".git", "templates", ".pytest_cache", ".ruff_cache")
            for part in c_yaml.parts
        ):
            continue
        c_dir = c_yaml.parent.resolve()
        if c_dir not in seen_comps:
            seen_comps.add(c_dir)
            comp_results.append(update_component(c_dir, dry_run=dry_run, check=check))

    seen_pipes: set[Path] = set()
    for p_yaml in sorted(target.rglob("pipeline.yaml")):
        if any(
            part in (".venv", ".git", "templates", ".pytest_cache", ".ruff_cache")
            for part in p_yaml.parts
        ):
            continue
        p_dir = p_yaml.parent.resolve()
        if p_dir not in seen_pipes:
            seen_pipes.add(p_dir)
            pipe_results.append(update_pipeline(p_dir, dry_run=dry_run, check=check))

    # If neither found, attempt single update on target
    if not comp_results and not pipe_results:
        if (target / "src").is_dir():
            comp_results.append(update_component(target, dry_run=dry_run, check=check))
        else:
            pipe_results.append(update_pipeline(target, dry_run=dry_run, check=check))

    return comp_results, pipe_results
