from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from PySide6 import QtCore, QtWidgets
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkFiltersSources import vtkCylinderSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer

from astermax.audit.store import AuditStore
from astermax.domain.models import EvidenceClass, ProjectSnapshot, WorkflowState
from astermax.orchestrator.state_machine import (
    InvalidTransition,
    WorkflowStateMachine,
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
        run_action = toolbar.addAction("Run Agentic Mock")
        open_action.triggered.connect(self.open_project)
        save_action.triggered.connect(self.save_project)
        run_action.triggered.connect(self.run_mock_workflow)

        splitter = QtWidgets.QSplitter()
        self.setCentralWidget(splitter)

        self.outline = QtWidgets.QTreeWidget()
        self.outline.setHeaderLabels(["Simulation Graph", "State"])
        splitter.addWidget(self.outline)

        center = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center)
        banner = QtWidgets.QLabel(
            "REFERENCE GEOMETRY — NO FEA RESULTS — PMV W0/W1"
        )
        banner.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(banner)

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
        right.addTab(self.reasoning, "Engineering Reasoning")
        right.addTab(self.evidence, "Evidence")
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
        self.vtk_widget.Initialize()
        self.vtk_widget.Start()

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
    def run_mock_workflow(self) -> None:
        if self.machine.state != WorkflowState.NEW:
            self.statusBar().showMessage(
                "Mock workflow starts only from NEW. Open/create a fresh project."
            )
            return
        worker = MockWorkflowWorker()
        worker.signals.progress.connect(self._apply_mock_transition)
        worker.signals.completed.connect(
            lambda: self.statusBar().showMessage(
                "Mock workflow reached MODEL_REVIEW with audited transitions."
            )
        )
        worker.signals.failed.connect(self._show_error)
        self.thread_pool.start(worker)

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
