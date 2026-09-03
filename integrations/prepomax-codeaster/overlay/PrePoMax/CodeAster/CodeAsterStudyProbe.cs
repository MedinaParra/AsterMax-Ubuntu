using System;
using System.Collections.Generic;
using System.IO;
using CaeModel;

namespace PrePoMax.CodeAster
{
    /// <summary>
    /// Headless CI probe that exercises PrePoMax's real INP model import followed by
    /// CodeAsterModelTranslator.WriteStudy(). No solver results are fabricated.
    /// </summary>
    public static class CodeAsterStudyProbe
    {
        public static int Run(string[] args)
        {
            try
            {
                if (args == null || args.Length != 2)
                {
                    Console.Error.WriteLine("Usage: PrePoMax.exe --codeaster-generate-probe <source.inp> <output-directory>");
                    return 64;
                }

                string inputFile = Path.GetFullPath(args[0]);
                string outputDirectory = Path.GetFullPath(args[1]);
                if (!File.Exists(inputFile))
                    throw new FileNotFoundException("Source PrePoMax/CalculiX INP does not exist.", inputFile);
                Directory.CreateDirectory(outputDirectory);

                FeModel model = new FeModel("CodeAsterGeneratedSmoke");
                List<string> importErrors = model.ImportModelFromInpFile(inputFile, Console.WriteLine);
                if (importErrors != null && importErrors.Count > 0)
                    throw new InvalidDataException("PrePoMax INP import reported errors: " + String.Join(" | ", importErrors));
                if (model.Mesh == null || model.Mesh.Nodes == null || model.Mesh.Nodes.Count != 4)
                    throw new InvalidDataException("Imported FeModel does not contain the expected four nodes.");
                if (model.Mesh.Elements == null || model.Mesh.Elements.Count != 1)
                    throw new InvalidDataException("Imported FeModel does not contain the expected tetrahedral element.");
                if (model.Materials == null || model.Materials.Count != 1)
                    throw new InvalidDataException("Imported FeModel does not contain exactly one material.");
                if (model.StepCollection == null || model.StepCollection.StepsList == null || model.StepCollection.StepsList.Count == 0)
                    throw new InvalidDataException("Imported FeModel contains no analysis step.");

                CodeAsterCaseOptions options = new CodeAsterCaseOptions
                {
                    JobName = "smoke",
                    WorkingDirectory = outputDirectory,
                    Version = "stable",
                    NumCpus = 1,
                    MemoryMB = 2048,
                    TimeLimitSeconds = 600
                };

                CodeAsterTranslationResult result = CodeAsterModelTranslator.WriteStudy(model, options);
                AssertFile(result.MeshFileName, ".mail");
                AssertFile(result.CommandFileName, ".comm");
                AssertFile(result.ExportFileName, ".export");

                string comm = File.ReadAllText(result.CommandFileName);
                if (!comm.Contains("MECA_STATIQUE"))
                    throw new InvalidDataException("Generated Code_Aster command file contains no MECA_STATIQUE operator.");
                if (!comm.Contains(CodeAsterResultBridge.DeplTitle) || !comm.Contains(CodeAsterResultBridge.StressNormalTitle))
                    throw new InvalidDataException("Generated command file does not contain the required result-table bridge.");

                string exportText = File.ReadAllText(result.ExportFileName);
                if (!exportText.Contains("F resu smoke.resu R 8"))
                    throw new InvalidDataException("Generated export file does not declare the .resu result unit.");
                if (!exportText.Contains("F rmed smoke.rmed R 80"))
                    throw new InvalidDataException("Generated export file does not declare the RMED result unit.");

                Console.WriteLine("Code_Aster FeModel study generation probe: PASS");
                Console.WriteLine("Nodes: " + model.Mesh.Nodes.Count);
                Console.WriteLine("Elements: " + model.Mesh.Elements.Count);
                Console.WriteLine("Materials: " + model.Materials.Count);
                Console.WriteLine("Steps: " + model.StepCollection.StepsList.Count);
                Console.WriteLine("Warnings: " + result.Warnings.Count);
                foreach (string warning in result.Warnings) Console.WriteLine("WARNING: " + warning);
                Console.WriteLine("MAIL: " + result.MeshFileName);
                Console.WriteLine("COMM: " + result.CommandFileName);
                Console.WriteLine("EXPORT: " + result.ExportFileName);
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("Code_Aster FeModel study generation probe: FAIL");
                Console.Error.WriteLine(ex.ToString());
                return 1;
            }
        }

        private static void AssertFile(string path, string extension)
        {
            if (String.IsNullOrWhiteSpace(path) || !File.Exists(path) || new FileInfo(path).Length == 0)
                throw new InvalidDataException("Generated " + extension + " file does not exist or is empty: " + path);
        }
    }
}
