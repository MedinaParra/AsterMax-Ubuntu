from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from astermax.credibility import canonical_sha256
from .tet_quality import tetra_mean_ratio, tetra_mean_ratio_cayley_menger


class WorstElementInspectorError(ValueError):
    pass


@dataclass(frozen=True)
class WorstElementQualitySnapshot:
    schema: str
    metric: str
    element_count: int
    quality_minimum: float
    quality_p10: float
    quality_median: float
    quality_maximum: float
    histogram_edges: tuple[float, ...]
    histogram_counts: tuple[int, ...]
    worst_elements: tuple[dict[str, Any], ...]
    crosscheck_max_abs_delta: float
    crosscheck_tolerance: float
    crosscheck_verified: bool
    ansys_metric_equivalence: bool
    industrial_acceptance_threshold_declared: bool
    snapshot_sha256: str


def _validated_mesh(nodes_mm: np.ndarray, elements: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nodes = np.asarray(nodes_mm, dtype=float)
    elems = np.asarray(elements, dtype=np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not np.all(np.isfinite(nodes)):
        raise WorstElementInspectorError("nodes_mm must have finite shape (n, 3)")
    if elems.ndim != 2 or elems.shape[1] != 10 or elems.shape[0] == 0:
        raise WorstElementInspectorError("elements must contain at least one TET10")
    if np.any(elems < 0) or np.any(elems >= nodes.shape[0]):
        raise WorstElementInspectorError("elements contains an out-of-range node index")
    return nodes, elems


def _oblique(points_mm: np.ndarray) -> np.ndarray:
    p = np.asarray(points_mm, dtype=float)
    return np.column_stack((p[:, 0] + 0.35 * p[:, 1], p[:, 2] + 0.20 * p[:, 1]))


def _quality_arrays(nodes: np.ndarray, elems: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    primary = np.asarray([tetra_mean_ratio(nodes[conn[:4]]) for conn in elems], dtype=float)
    secondary = np.asarray([tetra_mean_ratio_cayley_menger(nodes[conn[:4]]) for conn in elems], dtype=float)
    if not np.all(np.isfinite(primary)) or not np.all(np.isfinite(secondary)):
        raise WorstElementInspectorError("tetra quality contains non-finite values")
    return primary, secondary


def build_worst_element_quality_snapshot(
    *,
    nodes_mm: np.ndarray,
    elements: np.ndarray,
    tetra_quality: dict[str, Any],
    worst_count: int = 12,
) -> WorstElementQualitySnapshot:
    nodes, elems = _validated_mesh(nodes_mm, elements)
    if tetra_quality.get("schema") != "AsterMaxTetMeanRatioQualityV1":
        raise WorstElementInspectorError("C4.6 tetra quality evidence is required")
    if bool(tetra_quality.get("ansys_metric_equivalence")):
        raise WorstElementInspectorError("ANSYS_METRIC_EQUIVALENCE_NOT_DEMONSTRATED")
    if not bool(tetra_quality.get("crosscheck_verified")):
        raise WorstElementInspectorError("TETRA_MEAN_RATIO_CROSSCHECK_FAILED")
    if int(tetra_quality.get("element_count", -1)) != elems.shape[0]:
        raise WorstElementInspectorError("tetra quality element count does not match mesh")
    count = int(worst_count)
    if count < 1:
        raise WorstElementInspectorError("worst_count must be positive")

    q, qc = _quality_arrays(nodes, elems)
    delta = float(np.max(np.abs(q - qc)))
    tolerance = float(tetra_quality["crosscheck_tolerance"])
    if delta > tolerance:
        raise WorstElementInspectorError("TETRA_MEAN_RATIO_CROSSCHECK_FAILED")

    checks = (
        (float(np.min(q)), float(tetra_quality["minimum"]), "minimum"),
        (float(np.percentile(q, 10.0)), float(tetra_quality["percentile_10"]), "p10"),
        (float(np.median(q)), float(tetra_quality["median"]), "median"),
        (float(np.max(q)), float(tetra_quality["maximum"]), "maximum"),
    )
    for actual, expected, name in checks:
        if not np.isclose(actual, expected, rtol=1.0e-11, atol=1.0e-12):
            raise WorstElementInspectorError(f"tetra quality {name} does not match C4.6 evidence")

    projected_nodes = _oblique(nodes)
    low = projected_nodes.min(axis=0)
    high = projected_nodes.max(axis=0)
    span = high - low
    if np.any(span <= 0.0):
        raise WorstElementInspectorError("mesh projection has zero span")

    order = np.lexsort((np.arange(q.size, dtype=np.int64), q))
    worst_rows: list[dict[str, Any]] = []
    for rank, element_index in enumerate(order[: min(count, q.size)], start=1):
        corners = nodes[elems[element_index, :4]]
        centroid = np.mean(corners, axis=0)
        projected_corners = (_oblique(corners) - low) / span
        projected_centroid = (_oblique(centroid[None, :])[0] - low) / span
        worst_rows.append(
            {
                "rank": rank,
                "element_index": int(element_index),
                "quality": float(q[element_index]),
                "crosscheck_quality": float(qc[element_index]),
                "centroid_mm": [float(v) for v in centroid],
                "projected_centroid": [float(v) for v in projected_centroid],
                "projected_corners": [[float(x), float(y)] for x, y in projected_corners],
            }
        )

    hist_edges = np.linspace(0.0, 1.0, 11)
    hist_counts, _ = np.histogram(q, bins=hist_edges)
    core = {
        "schema": "AsterMaxWorstElementQualityInspectorV1",
        "metric": str(tetra_quality["metric"]),
        "element_count": int(q.size),
        "quality_minimum": float(np.min(q)),
        "quality_p10": float(np.percentile(q, 10.0)),
        "quality_median": float(np.median(q)),
        "quality_maximum": float(np.max(q)),
        "histogram_edges": tuple(float(v) for v in hist_edges),
        "histogram_counts": tuple(int(v) for v in hist_counts),
        "worst_elements": tuple(worst_rows),
        "crosscheck_max_abs_delta": delta,
        "crosscheck_tolerance": tolerance,
        "crosscheck_verified": True,
        "ansys_metric_equivalence": False,
        "industrial_acceptance_threshold_declared": False,
    }
    return WorstElementQualitySnapshot(**core, snapshot_sha256=canonical_sha256(core))


def install_worst_element_quality_tab(notebook: Any) -> Callable[[dict[str, Any]], None]:
    """Install native mesh-quality diagnostics and return a strict payload binder."""
    import tkinter as tk
    from tkinter import ttk

    panel = ttk.Frame(notebook, padding=12)
    notebook.add(panel, text="Mesh Quality")
    panel.columnconfigure(0, weight=3)
    panel.columnconfigure(1, weight=2)
    panel.rowconfigure(2, weight=1)

    ttk.Label(panel, text="Cross-Checked TET10 Quality Inspector", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(
        panel,
        text="Mean-ratio distribution and worst TET10 locations. The metric is independently cross-checked and is not labelled as ANSYS Element Quality or an industrial rejection criterion.",
        wraplength=900,
    ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))

    canvas = tk.Canvas(panel, background="#20252b", highlightthickness=1)
    canvas.grid(row=2, column=0, sticky="nsew", padx=(0, 10))
    info = tk.Text(panel, width=46, height=30, wrap="word", state="disabled")
    info.grid(row=2, column=1, sticky="nsew")

    def bind(payload: dict[str, Any]) -> None:
        snapshot = build_worst_element_quality_snapshot(
            nodes_mm=np.asarray(payload["nodes_mm"], dtype=float),
            elements=np.asarray(payload["elements"], dtype=np.int64),
            tetra_quality=payload["tetra_quality"],
        )
        canvas.delete("all")
        width = max(int(canvas.winfo_width()), 600)
        height = max(int(canvas.winfo_height()), 430)
        margin = 30.0
        edge_pairs = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
        for row in reversed(snapshot.worst_elements):
            pts = np.asarray(row["projected_corners"], dtype=float)
            screen = np.column_stack((margin + pts[:, 0] * (width - 2 * margin), height - margin - pts[:, 1] * (height - 2 * margin)))
            line_width = 3 if row["rank"] <= 3 else 1
            outline = "#ff5f56" if row["rank"] <= 3 else "#d8a657"
            for a, b in edge_pairs:
                canvas.create_line(float(screen[a, 0]), float(screen[a, 1]), float(screen[b, 0]), float(screen[b, 1]), fill=outline, width=line_width)
            cx, cy = row["projected_centroid"]
            sx = margin + cx * (width - 2 * margin)
            sy = height - margin - cy * (height - 2 * margin)
            radius = 6 if row["rank"] <= 3 else 4
            canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill=outline, outline="")
            if row["rank"] <= 5:
                canvas.create_text(sx + 8, sy - 8, anchor="sw", fill="#ffffff", text=f"E{row['element_index']} · q={row['quality']:.3f}")

        counts = snapshot.histogram_counts
        max_count = max(max(counts), 1)
        chart_left = 30
        chart_top = height - 115
        chart_width = min(width - 60, 420)
        chart_height = 75
        for i, count in enumerate(counts):
            x0 = chart_left + i * chart_width / len(counts)
            x1 = chart_left + (i + 1) * chart_width / len(counts) - 2
            y1 = chart_top + chart_height
            y0 = y1 - chart_height * count / max_count
            canvas.create_rectangle(x0, y0, x1, y1, fill="#6f7f8f", outline="")
        canvas.create_text(chart_left, chart_top - 8, anchor="sw", fill="#c5ccd3", text="Mean-ratio histogram 0 → 1")

        lines = [
            f"Elements: {snapshot.element_count}",
            f"Mean ratio min: {snapshot.quality_minimum:.4f}",
            f"p10: {snapshot.quality_p10:.4f}",
            f"median: {snapshot.quality_median:.4f}",
            f"max: {snapshot.quality_maximum:.4f}",
            "",
            "Independent cross-check",
            f"max |Δq|: {snapshot.crosscheck_max_abs_delta:.3e}",
            f"tolerance: {snapshot.crosscheck_tolerance:.3e}",
            "verified: TRUE",
            "",
            "Worst TET10 (zero-based element index)",
        ]
        for row in snapshot.worst_elements:
            x, y, z = row["centroid_mm"]
            lines.append(f"#{row['rank']:02d}  E{row['element_index']}  q={row['quality']:.4f}  C=({x:.2f}, {y:.2f}, {z:.2f}) mm")
        lines.extend(
            [
                "",
                "Evidence boundary",
                "No industrial quality threshold is declared.",
                "Not ANSYS Element Quality; ansys_metric_equivalence=false.",
                f"Inspector SHA\n{snapshot.snapshot_sha256}",
            ]
        )
        info.configure(state="normal")
        info.delete("1.0", "end")
        info.insert("1.0", "\n".join(lines))
        info.configure(state="disabled")

    return bind
