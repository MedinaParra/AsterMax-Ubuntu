# C12.08 — welded (bonded) joints for native Windows Code_Aster

C12.08 adds explicit welded joints to the AsterMax model bridge. A native
`CaeModel.Tie` is exported as linear displacement constraints between the selected
surfaces. Existing contact pairs keep their contact and friction laws.

## User workflow

Open **Conexiones → Unión bonded**, select the master and slave surfaces, and set
an explicit positive position tolerance. **Ajustar geometría** must be **No**.
The initial tolerance for a newly created joint is 0.05 mm; it must be reviewed
for the actual geometry. The tolerance selects eligible slave nodes and does
not move or close the geometric gap.

**Editar unión** opens the existing native constraint editor. The project keeps
the native serializable `Tie` type, surface selections and undo commands. The
automatic contact generator is disabled whenever an active bonded joint exists.
Mixed models can define their additional contact pairs manually. This prevents
automatic detection from adding contact laws over existing welded interfaces.

Force properties explicitly say **por nodo**. A native concentrated nodal force
is applied at every selected node; C12.08 does not reinterpret it as a total
force. **Información de la solución** displays both the exported components per
node and their resultant, together with the bonded audit. Gravity, when enabled,
is identified as an additional contribution.

## Mechanical formulation

The first bonded implementation supports linear, small-displacement **TETRA4**
solid meshes with **TRIA3** selected faces. Other supported solid element families
remain available for studies without bonded joints. A clear error blocks bonded
faces from an unsupported family.

For each eligible slave node, the exporter finds the closest triangle within
the selected master surface and retrieves its adjacent volume tetrahedron. It
evaluates that tetrahedron's affine shape functions at the **actual slave
coordinates**. It writes three equations, one for each translation component:

```
u_slave - sum_i(N_i(x_slave) * u_master_i) = 0
```

The weights reproduce constants and coordinates:

```
sum_i N_i = 1
sum_i N_i * x_master_i = x_slave
```

These identities reproduce translations, small rigid rotations and other affine
displacement fields. They also preserve force and moment balance for the internal
constraint forces across an admitted gap. No mesh node is repositioned and no
weld material or weld bead geometry is created. This is a massless kinematic
idealization; it does not predict local weld throat stress or weld strength.

The choice of actual-coordinate interpolation matters when a gap is present.
Code_Aster's documented `LIAISON_MAIL`/`MASSIF` projection treats an out-of-volume
slave point at the projected master boundary. Equal translations at two separated
points alone would not reproduce a general rigid rotation across that gap.
C12.08 therefore writes explicit `LIAISON_DDL` equations using ordered singleton
`GROUP_NO` entries. The primary command reference is
[Code_Aster v16 U4.44.01, AFFE_CHAR_MECA](https://code-aster.org/doc/v16/man_u/u4/u4.44.01.pdf).

## Shared nodes, supports and rank

Multiple joints can meet at an edge or corner. The planner checks the equations
together with all prescribed translation components. Sparse incremental rank
reduction retains the original independent equations and omits equations already
implied by earlier joints or prescribed supports. Nonzero imposed displacements
are included in the consistency calculation.

Contradictory imposed displacements, uncertain numerical rank, excessive sparse
fill, degenerate master tetrahedra and excessive extrapolation block export with
an actionable error. Duplicate prescribed support DOFs are also rejected rather
than producing repeated Lagrange multipliers. There is no fallback that silently
deletes an entire joint or changes a contact law.

Changing a joint's activation, surface names, tolerance or geometry-adjustment
setting changes the model fingerprint. Existing surface and mesh-group membership
checks remain part of that fingerprint. A previous result therefore cannot stay
current after a bonded definition changes.

## Audit files

The native export manifest contains `bonded_pair_count` and a
`bonded_mpc_report`. This report records the algorithm, included gaps, selected
and bound slave nodes, excluded nodes outside the tolerance, raw equations,
independent equations and eliminated redundant equations. It includes a separate
entry for every joint.

The accompanying `<analysis>.bonded-mpc.json` records each binding's master
tetrahedron, master nodes, weights, slave node, gap and exported components.
It is input/export evidence, not a numerical result. An interface with no eligible
slave nodes is rejected. Partly unmatched interfaces are explicitly reported so
the user can revise the surface scope or tolerance.

## Verification

The release workflow retains the previous native Code_Aster, MED import, fatal
diagnostic, stale-result, contact-orientation, STEP and Windows x64 checks.
C12.08 adds:

- Production C# bonded-planner checks for gaps, affine fields, shared nodes,
  repeated joints, multi-body cycles, support consistency and unchanged loads.
- A separate synthetic nonmatching TETRA4 assembly, with two bonded patches
  sharing slave edge nodes and an exact 2.5 mm gap.
- Independent parsing of the generated deck to check affine identities and the
  support-inclusive constraint rank before the solver runs.
- A real native Windows load case to check force transfer, support reactions,
  force and moment balance, and MED/table agreement.
- A real native Windows prescribed-rotation case to check gap kinematics and
  consistency with nonzero displacement supports.
- Native model-fingerprint regressions covering changes to the bonded law and
  selected regions.

Only independently generated synthetic geometry belongs in public CI. A private
user project must not be committed or uploaded to public workflow artifacts.
Successful synthetic verification does not constitute a completed numerical
analysis or mesh-convergence assessment of a user's project.

## Runtime and distribution

The target remains **Windows x64 with native Code_Aster**. The package does not
substitute another solver or fabricate numerical results. The Code_Aster runtime
installer is obtained from its original publisher through the existing setup
workflow; it is not redistributed in the application archive. Existing notices,
licenses, provenance checks and validated STEP import fixes remain included.
