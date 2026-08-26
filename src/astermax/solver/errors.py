class SolverBridgeError(RuntimeError):
    """Base class for fail-closed solver bridge errors."""


class UnsupportedSolverCapability(SolverBridgeError):
    pass


class SolverEvidenceError(SolverBridgeError):
    pass
