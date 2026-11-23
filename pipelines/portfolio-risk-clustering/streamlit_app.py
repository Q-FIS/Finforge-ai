"""Streamlit web application for FinForge.

Auto-generated for 'portfolio-risk-clustering' by FinForge AI CLI (finforge create-ui).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st

# -----------------------------------------------------------------------------
# Configuration and Path Resolution
# -----------------------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent
LOCAL_COMPS = PIPELINE_DIR / "components"
YAML_PATH = PIPELINE_DIR / "pipeline.yaml"

# Add local component src directories to sys.path
if LOCAL_COMPS.is_dir():
    for comp_path in sorted(LOCAL_COMPS.glob("*/src")):
        if comp_path.is_dir() and str(comp_path) not in sys.path:
            sys.path.insert(0, str(comp_path))

# Search workspace root components
for parent in PIPELINE_DIR.parents:
    ws_comps = parent / "components"
    if ws_comps.is_dir():
        for comp_path in sorted(ws_comps.glob("*/src")):
            if comp_path.is_dir() and str(comp_path) not in sys.path:
                sys.path.insert(0, str(comp_path))

from finforge import ComponentRegistry, Pipeline  # noqa: E402
from finforge.pipeline.serialization import (  # noqa: E402
    PipelineDocument,
    compute_document_execution_order,
    load_pipeline_document,
)

# -----------------------------------------------------------------------------
# Page Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FinForge AI — portfolio-risk-clustering",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #64748b;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Pipeline & Registry Helpers
# -----------------------------------------------------------------------------
@st.cache_resource
def get_registry() -> ComponentRegistry:
    """Discover and cache local and workspace components."""
    registry = ComponentRegistry()
    search_paths = [LOCAL_COMPS]
    for parent in PIPELINE_DIR.parents:
        ws_comps = parent / "components"
        if ws_comps.is_dir() and ws_comps not in search_paths:
            search_paths.append(ws_comps)
    registry.discover(search_paths=search_paths)
    return registry


def get_pipeline_doc() -> PipelineDocument:
    """Load the declarative pipeline document."""
    return load_pipeline_document(YAML_PATH)


def build_pipeline_instance(
    config_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[Pipeline, list[str]]:
    """Build a validated Pipeline instance with optional configuration overrides."""
    registry = get_registry()
    doc = get_pipeline_doc()
    pipeline = Pipeline(
        name=doc.name,
        registry=registry,
        description=doc.description,
        metadata=doc.metadata,
    )
    for node in doc.nodes:
        cfg = dict(node.config)
        if config_overrides and node.id in config_overrides:
            cfg.update(config_overrides[node.id])
        pipeline.add(node.id, node.component, config=cfg)

    for edge in doc.edges:
        pipeline.connect(
            edge.source_node,
            edge.source_port,
            edge.destination_node,
            edge.destination_port,
        )

    pipeline.validate()
    order = pipeline.execution_order()
    return pipeline, order


# -----------------------------------------------------------------------------
# Application State & Data Loading
# -----------------------------------------------------------------------------
doc = get_pipeline_doc()
registry = get_registry()

# -----------------------------------------------------------------------------
# Sidebar: Pipeline Metadata & Configurations
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ FinForge AI")
    st.markdown(f"**Pipeline:** `{doc.name}`")
    if doc.description:
        st.caption(f"{doc.description}")
    st.caption(f"Format Version: `{doc.format_version}`")

    st.divider()
    st.subheader("⚙️ Node Configurations")
    st.info("Tune node hyperparameters below:")

    node_configs: dict[str, dict[str, Any]] = {}
    for node in doc.nodes:
        with st.expander(f"🔹 {node.id} ({node.component})", expanded=False):
            if not node.config:
                st.caption("No configurable parameters.")
                node_configs[node.id] = {}
            else:
                current_cfg: dict[str, Any] = {}
                for k, v in node.config.items():
                    widget_key = f"cfg_{node.id}_{k}"
                    if isinstance(v, bool):
                        current_cfg[k] = st.checkbox(f"{k}", value=v, key=widget_key)
                    elif isinstance(v, int):
                        current_cfg[k] = st.number_input(
                            f"{k}", value=v, step=1, key=widget_key
                        )
                    elif isinstance(v, float):
                        current_cfg[k] = st.number_input(
                            f"{k}", value=v, format="%.4f", key=widget_key
                        )
                    elif isinstance(v, str):
                        current_cfg[k] = st.text_input(f"{k}", value=v, key=widget_key)
                    else:
                        raw = st.text_area(
                            f"{k} (JSON)", value=json.dumps(v), key=widget_key
                        )
                        try:
                            current_cfg[k] = json.loads(raw)
                        except Exception:
                            current_cfg[k] = v
                node_configs[node.id] = current_cfg

    st.divider()
    st.caption("FinForge AI — Scratch-First Modular AI")

# -----------------------------------------------------------------------------
# Main Header & Metric Summaries
# -----------------------------------------------------------------------------
st.markdown(f'<div class="main-header">{doc.name}</div>', unsafe_allow_html=True)
if doc.description:
    st.markdown(
        f'<div class="sub-header">{doc.description}</div>',
        unsafe_allow_html=True,
    )

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Pipeline Nodes", len(doc.nodes))
col_m2.metric("Port Connections", len(doc.edges))
try:
    topo_order = compute_document_execution_order(doc)
    col_m3.metric("Execution Steps", len(topo_order))
except Exception:
    topo_order = ["loader", "clusterer", "risk_evaluator"]
    col_m3.metric("Execution Steps", len(topo_order))
col_m4.metric("Discovered Components", len(registry))

# -----------------------------------------------------------------------------
# Main View Tabs
# -----------------------------------------------------------------------------
tab_run, tab_dag, tab_nodes, tab_yaml = st.tabs(
    [
        "🚀 Run Pipeline",
        "📊 Pipeline Topology",
        "🧩 Nodes & Ports",
        "📄 pipeline.yaml",
    ]
)

# -----------------------------------------------------------------------------
# Tab 1: Interactive Execution
# -----------------------------------------------------------------------------
with tab_run:
    st.subheader("Interactive Pipeline Execution")

    # Detect external input ports not covered by edges
    connected_inputs = {(e.destination_node, e.destination_port) for e in doc.edges}
    external_ports: list[tuple[str, str, str, str]] = []
    for node in doc.nodes:
        try:
            m = registry.get_manifest(node.component)
            for port_name, port_def in m.inputs.items():
                if (node.id, port_name) not in connected_inputs:
                    external_ports.append(
                        (node.id, node.component, port_name, port_def.type)
                    )
        except Exception:
            pass

    user_inputs: dict[str, dict[str, Any]] = {}

    if external_ports:
        st.markdown("#### External Pipeline Inputs")
        st.info("Inputs required by root or unlinked component ports:")
        for node_id, comp_name, port_name, port_type in external_ports:
            if node_id not in user_inputs:
                user_inputs[node_id] = {}
            label = f"**{node_id}**.{port_name} (`{port_type}` from `{comp_name}`)"
            inp_key = f"in_{node_id}_{port_name}"
            if port_type == "string":
                user_inputs[node_id][port_name] = st.text_area(label, key=inp_key)
            elif port_type == "integer":
                user_inputs[node_id][port_name] = st.number_input(
                    label, step=1, key=inp_key
                )
            elif port_type == "float":
                user_inputs[node_id][port_name] = st.number_input(
                    label, format="%.4f", key=inp_key
                )
            elif port_type == "boolean":
                user_inputs[node_id][port_name] = st.checkbox(label, key=inp_key)
            else:
                txt_val = st.text_area(f"{label} (JSON format)", key=inp_key)
                if txt_val.strip():
                    try:
                        user_inputs[node_id][port_name] = json.loads(txt_val)
                    except Exception:
                        user_inputs[node_id][port_name] = txt_val
    else:
        st.success("✓ All node inputs are routed internally via edges.")

    # Advanced input overrides
    with st.expander("🛠️ Advanced Input Overrides (JSON Mapping)", expanded=False):
        st.caption('Provide custom input overrides as `{"node_id": {"port": val}}`:')
        raw_override = st.text_area("Input Overrides JSON", value="{}", height=100)
        try:
            override_parsed = json.loads(raw_override) if raw_override.strip() else {}
            if isinstance(override_parsed, dict):
                for nid, ports in override_parsed.items():
                    if isinstance(ports, dict):
                        if nid not in user_inputs:
                            user_inputs[nid] = {}
                        user_inputs[nid].update(ports)
        except Exception as err:
            st.error(f"Invalid JSON format in overrides: {err}")

    st.write("")
    run_btn = st.button("🚀 Execute Pipeline", type="primary", use_container_width=True)

    if run_btn:
        with st.spinner("Executing pipeline through FinForge DAG runtime..."):
            start_time = time.perf_counter()
            try:
                pipeline_inst, exec_steps = build_pipeline_instance(
                    config_overrides=node_configs
                )
                filtered_inputs = {k: v for k, v in user_inputs.items() if v}
                result = pipeline_inst.run(
                    inputs=filtered_inputs if filtered_inputs else None
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                if result.success:
                    st.success(f"✓ Pipeline succeeded in {elapsed_ms:.2f} ms")
                else:
                    st.error(
                        f"✕ Finished with '{result.status}' in {elapsed_ms:.2f} ms"
                    )

                res_c1, res_c2, res_c3 = st.columns(3)
                res_c1.metric("Status", result.status.upper())
                res_c2.metric("Runtime", f"{elapsed_ms:.2f} ms")
                res_c3.metric("Nodes Executed", len(result.node_results))

                # Step-by-step breakdown
                st.subheader("📋 Step-by-Step Node Execution")
                for node_id in exec_steps:
                    node_res = result.node_results.get(node_id)
                    if not node_res:
                        continue
                    icon = "✅" if node_res.status == "succeeded" else "❌"
                    hdr = (
                        f"{icon} Step: **{node_id}** ({node_res.component_name}) "
                        f"— {node_res.duration_ms:.2f} ms"
                    )
                    with st.expander(hdr, expanded=True):
                        if node_res.error_details:
                            st.error(f"Error: {node_res.error_details}")

                        c_left, c_right = st.columns(2)
                        with c_left:
                            st.markdown("**Inputs Received:**")
                            if node_res.inputs:
                                st.json(node_res.inputs)
                            else:
                                st.caption("No upstream input values.")

                        with c_right:
                            st.markdown("**Outputs Generated:**")
                            if node_res.outputs:
                                for port_name, port_val in node_res.outputs.items():
                                    st.markdown(f"*Port:* `{port_name}`")
                                    if (
                                        isinstance(port_val, (list, tuple))
                                        and len(port_val) > 0
                                        and isinstance(port_val[0], dict)
                                    ):
                                        st.dataframe(port_val, use_container_width=True)
                                    elif isinstance(port_val, (int, float, str, bool)):
                                        st.info(f"{port_val}")
                                    else:
                                        st.json(port_val)
                            else:
                                st.caption("No output values produced.")

                # Final Outputs
                st.divider()
                st.subheader("📦 Final Pipeline Outputs")
                st.json(result.outputs)

                results_payload = {
                    "pipeline_name": doc.name,
                    "status": result.status,
                    "duration_ms": elapsed_ms,
                    "outputs": result.outputs,
                }
                st.download_button(
                    "📥 Download Results (JSON)",
                    data=json.dumps(results_payload, indent=2, default=str),
                    file_name=f"{doc.name}_results.json",
                    mime="application/json",
                )

            except Exception as exc:
                st.error(f"Execution Error: {exc}")
                import traceback

                st.code(traceback.format_exc(), language="python")

# -----------------------------------------------------------------------------
# Tab 2: DAG Visual Topology
# -----------------------------------------------------------------------------
with tab_dag:
    st.subheader("DAG Topology Flowchart")

    # Render Graphviz DOT
    dot_lines = [
        f'digraph "{doc.name}" {{',
        "  rankdir=LR;",
        '  graph [fontname="sans-serif", bgcolor="transparent"];',
        '  node [shape=box, style="rounded,filled", fillcolor="#eff6ff", '
        'color="#3b82f6", fontname="sans-serif", fontsize=11, margin="0.25,0.15"];',
        '  edge [color="#64748b", fontname="sans-serif", fontsize=9, '
        'fontcolor="#334155"];',
    ]
    for n in doc.nodes:
        dot_lines.append(f'  "{n.id}" [label="{n.id}\n[{n.component}]"];')
    for e in doc.edges:
        dot_lines.append(
            f'  "{e.source_node}" -> "{e.destination_node}" '
            f'[label="{e.source_port} → {e.destination_port}"];'
        )
    dot_lines.append("}")
    dot_markup = "\n".join(dot_lines)

    try:
        st.graphviz_chart(dot_markup)
    except Exception:
        mermaid_lines = ["flowchart LR"]
        for n in doc.nodes:
            mermaid_lines.append(f'    {n.id}["{n.id} ({n.component})"]')
        for e in doc.edges:
            p_lbl = f"{e.source_port} → {e.destination_port}"
            mermaid_lines.append(
                f'    {e.source_node} -->|"{p_lbl}"| {e.destination_node}'
            )
        st.markdown("```mermaid\n" + "\n".join(mermaid_lines) + "\n```")

    st.markdown("#### Topological Execution Sequence")
    for idx, step_name in enumerate(topo_order, 1):
        st.markdown(f"{idx}. `{step_name}`")

# -----------------------------------------------------------------------------
# Tab 3: Nodes & Ports Specification
# -----------------------------------------------------------------------------
with tab_nodes:
    st.subheader("Pipeline Nodes & Port Specifications")
    records = []
    for n in doc.nodes:
        comp_details = "Not Registered"
        inputs_desc = "None"
        outputs_desc = "None"
        try:
            m = registry.get_manifest(n.component)
            comp_details = f"{m.name} v{m.version} ({m.category})"
            if m.inputs:
                inputs_desc = ", ".join(f"{p} ({d.type})" for p, d in m.inputs.items())
            if m.outputs:
                outputs_desc = ", ".join(
                    f"{p} ({d.type})" for p, d in m.outputs.items()
                )
        except Exception:
            pass

        records.append(
            {
                "Node ID": n.id,
                "Component": n.component,
                "Manifest": comp_details,
                "Inputs": inputs_desc,
                "Outputs": outputs_desc,
                "Config": json.dumps(n.config),
            }
        )

    st.dataframe(records, use_container_width=True)

# -----------------------------------------------------------------------------
# Tab 4: Pipeline YAML
# -----------------------------------------------------------------------------
with tab_yaml:
    st.subheader("Declarative pipeline.yaml")
    if YAML_PATH.exists():
        raw_spec = YAML_PATH.read_text(encoding="utf-8")
        st.code(raw_spec, language="yaml")
        st.download_button(
            "📥 Download pipeline.yaml",
            data=raw_spec,
            file_name="pipeline.yaml",
            mime="application/x-yaml",
        )
    else:
        st.warning("pipeline.yaml file not found on disk.")
