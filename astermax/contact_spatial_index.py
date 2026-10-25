"""Deterministic AABB/BVH acceleration for TRI3 contact candidate search.

The index changes no contact physics. It only rejects master triangles whose expanded
axis-aligned bounding boxes cannot contain a slave point within the declared contact
search distance. The final finite-triangle projection and gap calculation remain in
the verified contact code, so exhaustive and BVH routes can be compared exactly.

Units: mm.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


class ContactSpatialIndexError(ValueError):
    """Raised when a contact spatial index cannot be built safely."""


@dataclass(frozen=True)
class TriangleAABB:
    triangle: tuple[int, int, int]
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    centroid: tuple[float, float, float]


@dataclass(frozen=True)
class _BVHNode:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    left: "_BVHNode | None" = None
    right: "_BVHNode | None" = None
    items: tuple[TriangleAABB, ...] = ()

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


@dataclass(frozen=True)
class TriangleAABBTree:
    root: _BVHNode
    triangle_count: int
    leaf_size: int

    def query_point(self, point: Sequence[float], *, distance_mm: float) -> tuple[tuple[int, int, int], ...]:
        """Return deterministic TRI3 candidates whose AABB is within distance of point."""
        p = _point3(point)
        distance = float(distance_mm)
        if not math.isfinite(distance) or distance < 0.0:
            raise ContactSpatialIndexError("query distance must be finite and non-negative")
        found: list[tuple[int, int, int]] = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            if not _point_near_box(p, node.minimum, node.maximum, distance):
                continue
            if node.is_leaf:
                for item in node.items:
                    if _point_near_box(p, item.minimum, item.maximum, distance):
                        found.append(item.triangle)
            else:
                # Push right first so traversal remains deterministic; final sorting also
                # guarantees equality independent of tree shape.
                if node.right is not None:
                    stack.append(node.right)
                if node.left is not None:
                    stack.append(node.left)
        return tuple(sorted(found))


def _point3(point: Sequence[float]) -> tuple[float, float, float]:
    if len(point) != 3:
        raise ContactSpatialIndexError("contact point must contain three coordinates")
    p = tuple(float(x) for x in point)
    if not all(math.isfinite(x) for x in p):
        raise ContactSpatialIndexError("contact point coordinates must be finite")
    return p


def _point_near_box(point, minimum, maximum, distance: float) -> bool:
    # Exact Euclidean point-to-AABB lower bound. If this exceeds the contact search
    # distance, no point on the triangle can be close enough to qualify.
    squared = 0.0
    for axis in range(3):
        value = point[axis]
        if value < minimum[axis]:
            delta = minimum[axis] - value
            squared += delta * delta
        elif value > maximum[axis]:
            delta = value - maximum[axis]
            squared += delta * delta
    return squared <= distance * distance


def _bounds(items: Sequence[TriangleAABB]):
    return (
        tuple(min(item.minimum[i] for item in items) for i in range(3)),
        tuple(max(item.maximum[i] for item in items) for i in range(3)),
    )


def _build(items: tuple[TriangleAABB, ...], leaf_size: int) -> _BVHNode:
    minimum, maximum = _bounds(items)
    if len(items) <= leaf_size:
        return _BVHNode(minimum, maximum, items=tuple(sorted(items, key=lambda item: item.triangle)))
    spans = tuple(maximum[i] - minimum[i] for i in range(3))
    axis = max(range(3), key=lambda i: (spans[i], -i))
    ordered = tuple(sorted(items, key=lambda item: (item.centroid[axis], item.triangle)))
    middle = len(ordered) // 2
    return _BVHNode(
        minimum,
        maximum,
        left=_build(ordered[:middle], leaf_size),
        right=_build(ordered[middle:], leaf_size),
    )


def build_triangle_aabb_tree(
    nodes: Sequence[Sequence[float]],
    triangles: Sequence[Sequence[int]],
    *,
    leaf_size: int = 8,
) -> TriangleAABBTree:
    """Build a deterministic median-split BVH over finite TRI3 AABBs."""
    if not isinstance(leaf_size, int) or leaf_size < 1:
        raise ContactSpatialIndexError("leaf_size must be a positive integer")
    points = tuple(_point3(point) for point in nodes)
    if not points:
        raise ContactSpatialIndexError("contact spatial index requires nodes")
    items = []
    seen = set()
    for raw in triangles:
        if len(raw) != 3:
            raise ContactSpatialIndexError("contact spatial index supports TRI3 only")
        tri = tuple(int(v) for v in raw)
        if len(set(tri)) != 3 or any(v < 0 or v >= len(points) for v in tri):
            raise ContactSpatialIndexError("TRI3 connectivity is invalid")
        if tri in seen:
            raise ContactSpatialIndexError("duplicate TRI3 connectivity is not allowed")
        seen.add(tri)
        coords = tuple(points[v] for v in tri)
        minimum = tuple(min(p[i] for p in coords) for i in range(3))
        maximum = tuple(max(p[i] for p in coords) for i in range(3))
        centroid = tuple(sum(p[i] for p in coords) / 3.0 for i in range(3))
        items.append(TriangleAABB(tri, minimum, maximum, centroid))
    if not items:
        raise ContactSpatialIndexError("contact spatial index requires at least one TRI3")
    frozen = tuple(items)
    return TriangleAABBTree(_build(frozen, leaf_size), len(frozen), leaf_size)
