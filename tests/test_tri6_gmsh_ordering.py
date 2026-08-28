from __future__ import annotations

import numpy as np

from astermax.fea.gmsh_bridge import _gmsh
from astermax.fea.tri6_traction import tri6_shape_functions


def test_tri6_shape_functions_match_gmsh_type9_reference_node_ordering():
    """Bind AsterMax TRI6 interpolation to Gmsh's actual type-9 contract.

    This prevents a surface-geometry or traction audit from silently assuming
    a different midside-node ordering than the mesher.  The test asks the Gmsh
    runtime itself for the reference-node coordinates and requires the AsterMax
    Lagrange basis to be Kronecker-delta at those nodes in the returned order.
    """
    gmsh = _gmsh(); gmsh.initialize()
    try:
        name, dim, order, num_nodes, local_coords, num_primary = gmsh.model.mesh.getElementProperties(9)
    finally:
        gmsh.finalize()

    assert str(name).lower().startswith("triangle")
    assert int(dim) == 2
    assert int(order) == 2
    assert int(num_nodes) == 6
    assert int(num_primary) == 3

    reference_nodes = np.asarray(local_coords, dtype=float).reshape((6, 2))
    interpolation = np.vstack([tri6_shape_functions(point) for point in reference_nodes])
    assert np.allclose(interpolation, np.eye(6), rtol=0.0, atol=2.0e-14), (
        "AsterMax TRI6 shape-function ordering does not match Gmsh element type 9; "
        f"reference_nodes={reference_nodes.tolist()}, interpolation={interpolation.tolist()}"
    )
