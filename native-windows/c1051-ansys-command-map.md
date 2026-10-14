# AsterMax C10.51 — ANSYS-style command map

Status: design contract for implementation. This file does **not** claim runtime functionality.

## Architectural rules

- STEP import creates/retains master BREP/topology and a lightweight tessellated face representation for the viewport.
- STEP import MUST NOT implicitly create the FEM volume mesh.
- Geometry, FEM mesh and results are separate representations of the same engineering model.
- FEM mesh is generated only by an explicit Generate Mesh action (or a future explicitly-approved Solve preflight policy; default is no implicit remesh).
- Hiding/showing FEM mesh is visibility-only: it MUST NOT delete, regenerate, reimport or retessellate geometry.
- Contacts are scoped to persistent geometry/topology identities and mapped to FEM groups when solving.
- Code_Aster native Windows remains the only solver.
- Ribbon commands reuse existing AsterMax/PrePoMax controller/domain actions where available. Do not duplicate solver/domain logic in UI handlers.

## ANSYS Mechanical → AsterMax command map

| Context | Mechanical concept | AsterMax command | Required behavior | Enable condition |
|---|---|---|---|---|
| Home | New | New | New model/project | always |
| Home | Open | Open | Open AsterMax model | always |
| Home | Save | Save | Persist model | model loaded |
| Home | Import Geometry | Import STEP | Import BREP and face preview only | model loaded |
| Home | Solve | Solve | Preflight → export → Code_Aster Windows → results | analysis structurally valid |
| Home | Named Selection | Named Selection | Persist reusable entity selection | selectable entities exist |
| Home | Coordinate System | Coordinate System | Create local CS for loads/BC | model loaded |
| Geometry | Material Assignment | Assign Material | Assign material to selected body/part | geometry selected |
| Geometry | Hide/Show Body | Hide/Show Geometry | Change CAD actor visibility only | geometry selected |
| Geometry | Transparency | Transparency | Change CAD actor opacity only | geometry selected |
| Geometry | Generate Mesh | Generate Mesh | Explicitly mesh selected body/part | meshable geometry selected |
| Connections | Contact Region | Contact | Create/edit geometry face-to-face contact | compatible faces/bodies selected |
| Connections | Automatic Connections | Auto Contacts | Detect candidate contacts; mark generated contacts for review | >=2 bodies |
| Mesh | Generate Mesh | Generate Mesh | Generate FEM representation without replacing master CAD | meshable geometry exists |
| Mesh | Update | Update Mesh | Regenerate only dirty/outdated mesh | mesh exists and is dirty |
| Mesh | Sizing | Sizing | Associate local size control with persistent BREP entity | geometry entity selected |
| Mesh | Refinement | Refinement | Local refinement control | meshable entity selected |
| Mesh | Show/Hide | Show/Hide Mesh | Toggle FEM actor visibility; one redraw; no remesh | mesh exists |
| Mesh | Statistics | Mesh Statistics | Nodes/elements/quality summary | mesh exists |
| Static Structural | Fixed Support | Fixed Support | Constrain selected geometric scope | valid scope selected |
| Static Structural | Displacement | Displacement | Prescribed displacement | valid scope selected |
| Static Structural | Force | Force | Vector force | valid scope selected |
| Static Structural | Pressure | Pressure | Surface pressure | face scope selected |
| Static Structural | Moment | Moment | Applied moment | valid scope selected |
| Static Structural | Gravity | Gravity | Body acceleration/load | analysis exists |
| Solution | Total Deformation | Total Deformation | Request/display displacement magnitude | solution/results available |
| Solution | Directional Deformation | Directional Deformation | Request/display displacement component | solution/results available |
| Solution | Equivalent Stress | Equivalent Stress | Request/display von Mises equivalent stress | solution/results available |
| Solution | Principal Stress | Principal Stress | Request/display principal stress | solution/results available |
| Solution | Reaction Force | Reaction Force | Evaluate reaction on constrained scope | solution/results available |
| Solution | Evaluate All | Evaluate All | Evaluate requested result objects | solution/results available |
| View | Fit | Fit | Fit active visible representation | visible actor exists |
| View | Isometric | Isometric | Camera only | visible actor exists |
| View | X/Y/Z | Standard Views | Camera only | visible actor exists |
| View | Edges | Edges | Geometry/mesh edge display; preserve C10.48 lazy element edges | visible actor exists |
| View | Mesh visibility | Show/Hide Mesh | Same mesh-visibility command as Mesh context | mesh exists |

## Model dependency/invalidation contract

```text
STEP/BREP
  ↓
Geometry ─────→ Materials
  ├───────────→ Connections
  ↓
Mesh
  ↓
Loads + Boundary Conditions
  ↓
Solution / Code_Aster
  ↓
Results
```

- Geometry/topology change → Mesh DIRTY, Solution DIRTY.
- Material change → Solution DIRTY; mesh remains valid unless element formulation requires otherwise.
- Contact change → Solution DIRTY; geometry and mesh remain unless contact meshing policy explicitly requires update.
- Mesh change → Solution DIRTY.
- Load/BC change → Solution DIRTY only.
- View/visibility/camera change → no engineering object becomes dirty.

## Tree state contract

- `Ready`: object is valid for the next dependency stage.
- `UpdateRequired`: upstream engineering data changed.
- `Incomplete`: required engineering input is missing.
- `Error`: validation failed.
- `Review`: automatically-generated engineering assumption (notably automatic contacts) requires engineer review.

## C10.51 implementation order

1. Resolve each mapped command against the existing Controller/Form/domain action.
2. Build a command registry so Ribbon and tree context menu call the same command implementation.
3. Implement context-sensitive enable/disable state from model/tree selection.
4. Add Geometry context actions: Assign Material, Generate Mesh, visibility/transparency.
5. Add independent FEM mesh overlay visibility.
6. Add Home Solve preflight without implicit STEP import/remesh side effects.
7. Add static guards proving Show/Hide Mesh cannot call mesher/import/delete paths.
8. Windows x64 Release compile and regression chain.

## Validation language

Until the Windows build/runtime evidence exists, all new C10.51 commands remain `NOT_RUN`. A command appearing in this map does not mean it is implemented or validated.
