from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from PySide6 import QtCore, QtWidgets
import vtkmodules.vtkInteractionStyle  # noqa: F401 - registers interaction styles
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401 - registers OpenGL backend
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkFiltersSources import vtkCylinderSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkDataSetMapper, vtkPolyDataMapper, vtkRenderer

from astermax.audit.store import AuditStore
from astermax.domain.models import EvidenceClass, ProjectSnapshot, WorkflowState
from astermax.orchestrator.state_machine import (
    InvalidTransition,
    WorkflowStateMachine,
)
from astermax.solver.contracts import SolverRequestV1, SolverRunManifestV1
from astermax.solver.result_loader import load_converted_solver_result
from astermax.ui.result_view import (
    RenderableResultField,
    discover_renderable_fields,
    load_verified_vtu,
)


MOCK_SEQUENCE = (
    (WorkflowState.INTENT_STRUCTURED, "A1", "Engineering intent structured.", False),
    (WorkflowState.GEOMETRY_READY, "A2", "Reference geometry inventoried.", False),
    (WorkflowState.PHYSICS_PROPOSED, "A3", "Physics proposal created.", False),
    (WorkflowState.MODEL_REVIEW, "HUMAN", "Physics proposal reviewed.", True),
)


class WorkerSignals(QtCore.QObject):
    progress = QtCore.Signal(object)
    completed = QtCore.Signal()
    failed = QtCore.Signal(str)


class MockWorkflowWorker(QtCore.QRunnable):
    """Background worker that emits requested transitions only.

    The deterministic state machine remains in the UI process and owns the
    actual transition decision.
    """

    def __init__(self) -> None:
        super().__init__()
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            for item in MOCK_SEQUENCE:
                time.sleep(0.15)
                self.signals.progress.emit(item)
            self.signals.completed.emit()
        except Exception as exc:  # pragma: no cover - defensive boundary
            self.signals.failed.emit(str(exc))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, audit_store: AuditStore) -> None:
        super().__init__()
        self.audit_store = audit_store
        self.project = ProjectSnapshot(
            project_id=f"pmv-{uuid.uuid4().hex[:8]}",
            name="Hub-Sprocket PMV",
            engineering_question=(
                "How does increasing gap alter load transfer and local response?"
            ),
            parameters={"gap_mm": 0.0},
        )
        self.machine = self._new_machine(self.project.state)
        self.thread_pool = QtCore.QThreadPool.globalInstance()
        self._active_workers: set[MockWorkflowWorker] = set()
        self._result_grid = None
        self._result_mapper: vtkDataSetMapper | None = None
        self._result_actor: vtkActor | None = None
        self._renderable_fields: list[RenderableResultField] = []
        self._validated_result = None
        self._validated_manifest: SolverRunManifestV1 | None = None
        self._validated_vtu_artifact = None
        self._vtk_initialized = False

        self.setWindowTitle("AsterMax Mechanical — Future Simulation PMV")
        self.resize(1500, 900)
        self._build_ui()
        self._populate_reference_geometry()
        self._refresh_views()

    def _new_machine(self, state: WorkflowState) -> WorkflowStateMachine:
        return WorkflowStateMachine(
            self.project.project_id,
            initial_state=state,
            event_sink=self.audit_store.append_event,
        )

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Project")
        open_action = toolbar.addAction("Open")
        save_action = toolbar.addAction("Save")
        result_action = toolbar.addAction("Open Validated Result")
        run_action = toolbar.addAction("Run Agentic Mock")
        open_action.triggered.connect(self.open_project)
        save_action.triggered.connect(self.save_project)
        result_action.triggered.connect(self.open_validated_result)
        run_action.triggered.connect(self.run_mock_workflow)

        splitter = QtWidgets.QSplitter()
        self.setCentralWidget(splitter)

        self.outline = QtWidgets.QTreeWidget()
        self.outline.setHeaderLabels(["Simulation Graph", "State"])
        splitter.addWidget(self.outline)

        center = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center)
        self.result_banner = QtWidgets.QLabel(
            "REFERENCE GEOMETRY — NO FEA RESULTS — PMV W0/W1"
        )
        self.result_banner.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.result_banner)

        result_controls = QtWidgets.QWidget()
        result_controls_layout = QtWidgets.QHBoxLayout(result_controls)
        result_controls_layout.setContentsMargins(0, 0, 0, 0)
        result_controls_layout.addWidget(QtWidgets.QLabel("Validated result field:"))
        self.result_field_combo = QtWidgets.QComboBox()
        self.result_field_combo.setEnabled(False)
        self.result_field_combo.currentIndexChanged.connect(self._apply_render_field)
        result_controls_layout.addWidget(self.result_field_combo, 1)
        self.result_field_info = QtWidgets.QLabel("No validated solver result loaded")
        result_controls_layout.addWidget(self.result_field_info)
        center_layout.addWidget(result_controls)

        self.vtk_widget = QVTKRenderWindowInteractor(center)
        center_layout.addWidget(self.vtk_widget, 1)
        splitter.addWidget(center)

        right = QtWidgets.QTabWidget()
        self.reasoning = QtWidgets.QPlainTextEdit()
        self.reasoning.setReadOnly(True)
        self.evidence = QtWidgets.QTableWidget(0, 4)
        self.evidence.setHorizontalHeaderLabels(
            ["From", "To", "Actor", "Evidence"]
        )
        self.evidence.horizontalHeader().setStretchLastSection(True)
        self.result_evidence = QtWidgets.QPlainTextEdit()
        self.result_evidence.setReadOnly(True)
        self.result_evidence.setPlainText(
            "No validated solver result loaded.\n"
            "Reference geometry must never be interpreted as FEA evidence."
        )
        right.addTab(self.reasoning, "Engineering Reasoning")
        right.addTab(self.evidence, "Evidence")
        right.addTab(self.result_evidence, "Result Evidence")
        splitter.addWidget(right)

        splitter.setSizes([300, 850, 350])
        self.statusBar().showMessage("Ready")

    def _populate_reference_geometry(self) -> None:
        self.renderer = vtkRenderer()
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)

        for radius, height, opacity in ((1.7, 0.8, 0.45), (0.9, 1.4, 0.85)):
            source = vtkCylinderSource()
            source.SetRadius(radius)
            source.SetHeight(height)
            source.SetResolution(96)
            source.Update()

            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(source.GetOutputPort())

            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetOpacity(opacity)
            self.renderer.AddActor(actor)

        self.renderer.ResetCamera()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        if self._vtk_initialized:
            return
        self.vtk_widget.Initialize()
        self.vtk_widget.Start()
        self._vtk_initialized = True
        self.vtk_widget.GetRenderWindow().Render()

    def _render_if_initialized(self) -> None:
        if self._vtk_initialized:
            self.vtk_widget.GetRenderWindow().Render()

    def _refresh_views(self) -> None:
        self.outline.clear()
        root = QtWidgets.QTreeWidgetItem(
            [self.project.name, self.machine.state.value]
        )
        self.outline.addTopLevelItem(root)
        for label in (
            "Engineering Intent",
            "Geometry",
            "Physics",
            "Model Review",
            "Mesh",
            "Solver",
            "Verification",
            "Experiments",
            "Surrogate",
            "RCA",
        ):
            root.addChild(QtWidgets.QTreeWidgetItem([label, "pending"]))
        root.setExpanded(True)

        self.reasoning.setPlainText(
            "\n".join(
                [
                    f"Project: {self.project.project_id}",
                    f"State: {self.machine.state.value}",
                    "",
                    "Engineering question:",
                    self.project.engineering_question,
                    "",
                    "Evidence policy:",
                    "• Agents may propose.",
                    "• Deterministic gates decide.",
                    "• Solver results are a separate evidence class.",
                    "• Surrogate predictions can never be labelled as FEA truth.",
                    "• Converted VTU artifacts are deterministic postprocess evidence, not solver-authored files.",
                ]
            )
        )
        self._refresh_evidence()
        self.statusBar().showMessage(f"Workflow state: {self.machine.state.value}")

    def _refresh_evidence(self) -> None:
        events = self.audit_store.list_events(self.project.project_id)
        self.evidence.setRowCount(len(events))
        for row_index, event in enumerate(events):
            values = (
                event["from_state"],
                event["to_state"],
                event["actor"],
                event["evidence_class"],
            )
            for column, value in enumerate(values):
                self.evidence.setItem(
                    row_index, column, QtWidgets.QTableWidgetItem(value)
                )

    @QtCore.Slot()
    def open_validated_result(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Open validated AsterMax solver run directory",
            "",
        )
        if not selected:
            return
        root = Path(selected).resolve()
        try:
            request_path = root / "input" / "solver_request.json"
            manifest_path = root / "output" / "manifest.json"
            if not request_path.is_file() or not manifest_path.is_file():
                raise ValueError(
                    "run directory must contain input/solver_request.json and output/manifest.json"
                )
            request = SolverRequestV1.model_validate_json(
                request_path.read_text(encoding="utf-8")
            )
            manifest = SolverRunManifestV1.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            result = load_converted_solver_result(root, request, manifest)
            grid, artifact = load_verified_vtu(root, result)
            fields = discover_renderable_fields(result, grid)
            self._show_validated_result(root, manifest, result, grid, artifact, fields)
        except Exception as exc:
            self._show_error(f"Validated result rejected: {exc}")

    def _show_validated_result(
        self,
        root: Path,
        manifest: SolverRunManifestV1,
        result,
        grid,
        artifact,
        fields: list[RenderableResultField],
    ) -> None:
        self._validated_manifest = manifest
        self._validated_result = result
        self._result_grid = grid
        self._validated_vtu_artifact = artifact
        self._renderable_fields = fields

        self.renderer.RemoveAllViewProps()
        self._result_mapper = vtkDataSetMapper()
        self._result_mapper.SetInputData(grid)
        self._result_actor = vtkActor()
        self._result_actor.SetMapper(self._result_mapper)
        self.renderer.AddActor(self._result_actor)

        self.result_field_combo.blockSignals(True)
        self.result_field_combo.clear()
        for field in fields:
            self.result_field_combo.addItem(field.label)
        self.result_field_combo.blockSignals(False)
        self.result_field_combo.setEnabled(True)

        source_hash = result.metadata.get("source_solver_artifact_sha256", "unknown")
        conversion_hash = result.metadata.get("conversion_manifest_sha256", "unknown")
        self.result_banner.setText(
            "AUTHENTIC SOLVER RESULT — source: SOLVER_RESULT → VTU: DETERMINISTIC_CALCULATION — "
            f"RMED {str(source_hash)[:12]}…"
        )
        self.result_evidence.setPlainText(
            "\n".join(
                [
                    "VALIDATED RESULT CHAIN",
                    f"Run directory: {root}",
                    f"Backend: {manifest.backend_id}",
                    f"Backend version: {manifest.backend_version}",
                    f"Termination: {manifest.termination.value}",
                    f"Source RMED SHA-256: {source_hash}",
                    f"Conversion manifest SHA-256: {conversion_hash}",
                    f"VTU SHA-256: {artifact.sha256}",
                    f"VTU bytes: {artifact.byte_size}",
                    "Source evidence: SOLVER_RESULT",
                    "VTU artifact evidence: DETERMINISTIC_CALCULATION",
                    "Displayed scalar fields: DERIVED / DETERMINISTIC_CALCULATION",
                    "No unit is inferred when the source MED does not deterministically provide one.",
                ]
            )
        )
        self.renderer.ResetCamera()
        self._apply_render_field(0)
        self._render_if_initialized()
        self.statusBar().showMessage("Validated solver result loaded; provenance chain verified.")

    @QtCore.Slot(int)
    def _apply_render_field(self, index: int) -> None:
        if (
            index < 0
            or index >= len(self._renderable_fields)
            or self._result_mapper is None
            or self._result_grid is None
        ):
            return
        field = self._renderable_fields[index]
        if field.vtk_association == "POINT":
            array = self._result_grid.GetPointData().GetArray(field.array_name)
            self._result_mapper.SetScalarModeToUsePointFieldData()
        elif field.vtk_association == "CELL":
            array = self._result_grid.GetCellData().GetArray(field.array_name)
            self._result_mapper.SetScalarModeToUseCellFieldData()
        else:
            self._show_error(f"Unsupported VTK association: {field.vtk_association}")
            return
        if array is None:
            self._show_error(f"Validated render array disappeared: {field.array_name}")
            return
        self._result_mapper.SelectColorArray(field.array_name)
        self._result_mapper.SetScalarRange(array.GetRange())
        self._result_mapper.ScalarVisibilityOn()
        value_range = array.GetRange()
        unit = field.unit or "source unit unspecified"
        self.result_field_info.setText(
            f"{field.derived_evidence_class} | range {value_range[0]:.6g} … {value_range[1]:.6g} | {unit}"
        )
        self._render_if_initialized()

    @QtCore.Slot()
    def run_mock_workflow(self) -> None:
        if self.machine.state != WorkflowState.NEW:
            self.statusBar().showMessage(
                "Mock workflow starts only from NEW. Open/create a fresh project."
            )
            return
        worker = MockWorkflowWorker()
        self._active_workers.add(worker)
        worker.signals.progress.connect(self._apply_mock_transition)
        worker.signals.completed.connect(
            lambda worker=worker: self._worker_completed(worker)
        )
        worker.signals.failed.connect(
            lambda message, worker=worker: self._worker_failed(worker, message)
        )
        self.thread_pool.start(worker)

    def _worker_completed(self, worker: MockWorkflowWorker) -> None:
        self._active_workers.discard(worker)
        self.statusBar().showMessage(
            "Mock workflow reached MODEL_REVIEW with audited transitions."
        )

    def _worker_failed(self, worker: MockWorkflowWorker, message: str) -> None:
        self._active_workers.discard(worker)
        self._show_error(message)

    @QtCore.Slot(object)
    def _apply_mock_transition(self, item: object) -> None:
        target, actor, reason, human_approved = item
        evidence = (
            EvidenceClass.USER_INPUT
            if actor == "HUMAN"
            else EvidenceClass.AGENT_PROPOSAL
        )
        try:
            self.machine.transition(
                target,
                actor=actor,
                evidence_class=evidence,
                reason=reason,
                human_approved=human_approved,
            )
            self.project.state = self.machine.state
            self._refresh_views()
        except InvalidTransition as exc:
            self._show_error(str(exc))

    def save_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save AsterMax project",
            f"{self.project.name}.astermax.json",
            "AsterMax Project (*.astermax.json);;JSON (*.json)",
        )
        if not path:
            return
        Path(path).write_text(
            self.project.model_dump_json(indent=2),
            encoding="utf-8",
        )
        self.statusBar().showMessage(f"Saved: {path}")

    def open_project(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open AsterMax project",
            "",
            "AsterMax Project (*.astermax.json);;JSON (*.json)",
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            self.project = ProjectSnapshot.model_validate(payload)
            self.machine = self._new_machine(self.project.state)
            self._refresh_views()
            self.statusBar().showMessage(f"Opened: {path}")
        except Exception as exc:
            self._show_error(f"Could not open project: {exc}")

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QtWidgets.QMessageBox.critical(self, "AsterMax", message)
