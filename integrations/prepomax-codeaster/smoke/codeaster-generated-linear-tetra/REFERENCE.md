# Analytical reference for the generated linear tetra smoke

This reference is independent of Code_Aster. It is the closed-form stiffness solution for the single linear tetrahedron used by `source.inp`.

## Geometry and material

Nodes:

- N1 = (0, 0, 0)
- N2 = (1, 0, 0)
- N3 = (0, 1, 0)
- N4 = (0, 0, 1)

The tetrahedron volume is

`V = 1/6 m^3`.

Material:

- `E = 210e9 Pa`
- `nu = 0.3`
- `G = E / (2(1+nu)) = 80.76923076923077e9 Pa`

Nodes N1, N2 and N3 are fixed in X/Y/Z. N4 is loaded by `FX = 1000 N` and remains free in X/Y/Z.

## Linear tetra kinematics

For this tetrahedron the N4 shape function is simply

`N4 = z`

so

`grad(N4) = (0, 0, 1)`.

With the first three nodes fixed, the only N4 displacement contributing to the applied X load is `u4x`. Its engineering shear strain is

`gamma_xz = du/dz = u4x`.

The reduced X-direction stiffness is therefore

`K44_xx = G * V`.

Hence

`u4x = FX / (G*V)`

`u4x = 1000 / (80.76923076923077e9 * 1/6)`

`u4x = 7.428571428571429e-8 m`.

No Y or Z load is applied and the reduced block has no coupling between this shear DOF and the remaining free N4 DOFs, therefore

- `u4y = 0`
- `u4z = 0`

## Stress and strain reference

The shear stress is constant in a one-element linear tetrahedron:

`tau_xz = G * gamma_xz`

`tau_xz = 6000 Pa`.

Code_Aster reports tensor shear strain `EPXZ`, not engineering shear `gamma_xz`, so

`EPXZ = gamma_xz / 2`

`EPXZ = 3.7142857142857144e-8`.

The ideal normal stress components for this load case are zero:

- `SIXX = 0`
- `SIYY = 0`
- `SIZZ = 0`

## CI contract

`reference-contract.json` compares the genuine Code_Aster `.resu` output against these values. Small absolute and relative tolerances are allowed only for floating-point/output formatting effects.

The reference values are never generated from the Code_Aster result itself; this prevents the regression test from becoming self-referential.
