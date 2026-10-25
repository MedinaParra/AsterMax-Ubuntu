import numpy as np

from astermax.fea.solver import solve_linear_static
from astermax.fea.tet4 import IsotropicMaterial, tet4_B_matrix, tet4_stiffness


def test_unit_tetra_volume_and_symmetry():
    xyz = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    b, volume = tet4_B_matrix(xyz)
    assert np.isclose(volume, 1/6)
    k = tet4_stiffness(xyz, IsotropicMaterial(210000., 0.3))
    assert k.shape == (12, 12)
    assert np.allclose(k, k.T, rtol=1e-12, atol=1e-9)
    assert b.shape == (6, 12)


def test_single_tetra_equilibrium_and_positive_energy():
    nodes = np.array([[0.,0.,0.],[10.,0.,0.],[0.,10.,0.],[0.,0.,10.]])
    elements = np.array([[0,1,2,3]])
    loads = np.zeros((4,3))
    loads[1,0] = 1000.0
    # Fix nodes 0,2,3 completely; node 1 remains free.
    fixed = [0,1,2, 6,7,8, 9,10,11]
    result = solve_linear_static(nodes, elements, IsotropicMaterial(210000.,0.3), loads, fixed)
    assert result.displacement_mm[1,0] > 0
    assert np.isclose(result.reactions_n[:,0].sum(), -1000.0, rtol=1e-10, atol=1e-7)
    assert np.isclose(result.reactions_n[:,1].sum(), 0.0, atol=1e-7)
    assert np.isclose(result.reactions_n[:,2].sum(), 0.0, atol=1e-7)
    assert result.element_von_mises_mpa[0] > 0
