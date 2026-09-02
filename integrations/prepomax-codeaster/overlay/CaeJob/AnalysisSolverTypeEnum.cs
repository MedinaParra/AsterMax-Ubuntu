using System;

namespace CaeJob
{
    /// <summary>
    /// Selects the finite-element engine used by an AnalysisJob.
    /// This is deliberately separate from CaeModel.SolverTypeEnum, which
    /// selects the matrix solver used internally by CalculiX.
    /// </summary>
    [Serializable]
    public enum AnalysisSolverTypeEnum
    {
        Calculix = 0,
        CodeAster = 1
    }
}
