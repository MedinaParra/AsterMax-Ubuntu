# AsterMax Mechanical 0.3 beta

Windows GUI developed from the workflow methodology contained in the uploaded Mechanical training manuals.

## Implemented application structure

- menu and contextual Ribbon;
- Outline tree with object-state indicators;
- central Graphics viewport;
- editable Details view;
- Graphics, Worksheet, Graph, Tabular Data and Messages tabs;
- workflow navigator: Preliminary Decisions, Preprocessing, Solution and Postprocessing;
- context commands that change with the selected Outline object.

## Implemented workflow

1. Import STEP, IGES or BREP geometry.
2. Assign materials and coordinate systems.
3. Create contacts and named selections.
4. Insert mesh controls and generate a finite-element mesh.
5. Add Static Structural, Modal, Thermal, Buckling or Submodel environments.
6. Configure Analysis Settings.
7. Insert supports and loads.
8. Validate and solve the model.
9. Insert deformation, stress, strain, reaction, contact, chart and probe results.
10. Review Worksheet, Graph, Tabular Data and Messages.

## Code_Aster integration

The Solver menu can configure a native Windows Code_Aster launcher, validate it with `--help`, execute an external `.export` file and export a starter `.comm` file. The current GUI beta uses a deterministic simulated solve for testing the complete interaction flow while the recovered AsterMax solver/model layer is integrated.

## Intellectual-property boundary

The application follows a general finite-element workflow and panel arrangement. It does not redistribute proprietary source code, logos, screenshots, icons or documentation. All visual elements in this beta are original AsterMax controls drawn with WinForms.

## Build

```powershell
dotnet publish windows/AsterMax.MechanicalGui/AsterMax.MechanicalGui.csproj `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true
```
