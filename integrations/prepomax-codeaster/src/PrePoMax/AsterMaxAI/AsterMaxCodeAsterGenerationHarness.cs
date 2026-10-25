using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using CaeGlobals;
using CaeModel;
using PrePoMax.CodeAster;

namespace PrePoMax.AsterMaxAI
{
    // C8.62 CI-only evidence harness. It consumes the already-qualified C8.60/C8.61 model,
    // persists it through native PMX, reopens it, and generates a Code_Aster study.
    // It deliberately does not launch Code_Aster and never claims solver verification.
    internal sealed class AsterMaxCodeAsterGenerationHarness
    {
        private readonly Controller _controller;
        public AsterMaxCodeAsterGenerationHarness(Controller controller) { _controller = controller; }

        public void RunIfRequested()
        {
            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_CODEASTER_GENERATION_FIXTURE"), "1", StringComparison.Ordinal)) return;
            string evidencePath = Environment.GetEnvironmentVariable("ASTERMAX_CODEASTER_GENERATION_EVIDENCE_PATH");
            string workDir = Environment.GetEnvironmentVariable("ASTERMAX_CODEASTER_GENERATION_WORKDIR");
            if (String.IsNullOrWhiteSpace(workDir)) workDir = Path.Combine(Path.GetTempPath(), "AsterMax_C862_CodeAster");
            string pmxPath = Path.Combine(workDir, "AsterMax_C862_Structural.pmx");

            bool sourceReady=false, unitBefore=false, pmxSaved=false, pmxReopened=false, unitAfter=false;
            bool materialPersisted=false, sectionPersisted=false, stepPersisted=false, fixedPersisted=false, loadPersisted=false;
            bool valuesPersisted=false, pmxRoundtrip=false, studyGenerated=false, commSemantics=false, mailNonEmpty=false, exportNonEmpty=false;
            bool translationWarningsClean=false, qualified=false;
            long pmxBytes=0, commBytes=0, mailBytes=0, exportBytes=0;
            string pmxSha="", commSha="", mailSha="", exportSha="", warningSummary="", error="";
            string commPath="", mailPath="", exportPath="";
            double persistedE=Double.NaN, persistedF1=Double.NaN;
            try
            {
                Directory.CreateDirectory(workDir);
                FeModel model=_controller.Model;
                sourceReady=HasQualifiedSource(model);
                if(!sourceReady) throw new InvalidOperationException("C8.62 requires the qualified C8.61 structural model in memory.");

                unitBefore=IsMmNMPa(model.UnitSystem);
                if(!unitBefore) throw new InvalidOperationException("Model is not locked to MM_TON_S_C / mm / N / MPa before PMX persistence.");

                _controller.SaveToPmx(pmxPath);
                pmxSaved=File.Exists(pmxPath) && new FileInfo(pmxPath).Length>0;
                if(!pmxSaved) throw new InvalidOperationException("Native SaveToPmx did not create a non-empty PMX file.");
                pmxBytes=new FileInfo(pmxPath).Length; pmxSha=HashFile(pmxPath);

                _controller.Open(pmxPath);
                model=_controller.Model;
                pmxReopened=model!=null && model.Mesh!=null && model.Mesh.Nodes.Count>0 && model.Mesh.Elements.Count>0;
                if(!pmxReopened) throw new InvalidOperationException("Native Open(PMX) did not restore a non-empty FE model.");
                unitAfter=IsMmNMPa(model.UnitSystem);

                Material material=model.Materials.ContainsKey("AsterMax_Steel_Demo")?model.Materials["AsterMax_Steel_Demo"]:null;
                Elastic elastic=material==null?null:material.GetProperty<Elastic>() as Elastic;
                materialPersisted=elastic!=null && elastic.YoungsPoissonsTemp!=null && elastic.YoungsPoissonsTemp.Length>0;
                if(materialPersisted) persistedE=elastic.YoungsPoissonsTemp[0][0];
                sectionPersisted=model.Sections.ContainsKey("AsterMax_Solid_Section") && model.Sections["AsterMax_Solid_Section"] is SolidSection;
                StaticStep step=model.StepCollection.GetStep("Static_Structural") as StaticStep;
                stepPersisted=step!=null;
                fixedPersisted=step!=null && step.BoundaryConditions.ContainsKey("Fixed_Support") && step.BoundaryConditions["Fixed_Support"] is FixedBC;
                CLoad load=step!=null && step.Loads.ContainsKey("Force_XMAX")?step.Loads["Force_XMAX"] as CLoad:null;
                loadPersisted=load!=null;
                if(load!=null) persistedF1=load.F1;
                valuesPersisted=Nearly(persistedE,210000.0) && Nearly(persistedF1,1000.0);
                pmxRoundtrip=pmxReopened && unitAfter && materialPersisted && sectionPersisted && stepPersisted && fixedPersisted && loadPersisted && valuesPersisted;
                if(!pmxRoundtrip) throw new InvalidOperationException("PMX structural/unit roundtrip did not preserve the qualified setup.");

                CodeAsterCaseOptions options=new CodeAsterCaseOptions();
                options.JobName="astermax_c862_static";
                options.WorkingDirectory=workDir;
                options.Version="stable";
                options.NumCpus=1;
                options.MemoryMB=4096;
                options.TimeLimitSeconds=600;
                CodeAsterTranslationResult result=CodeAsterModelTranslator.WriteStudy(model,options);
                commPath=result.CommandFileName; mailPath=result.MeshFileName; exportPath=result.ExportFileName;
                warningSummary=result.Warnings==null?"":String.Join(" | ",result.Warnings.ToArray());
                translationWarningsClean=result.Warnings!=null && result.Warnings.Count==0;

                studyGenerated=NonEmpty(commPath) && NonEmpty(mailPath) && NonEmpty(exportPath);
                if(studyGenerated)
                {
                    commBytes=new FileInfo(commPath).Length; mailBytes=new FileInfo(mailPath).Length; exportBytes=new FileInfo(exportPath).Length;
                    commSha=HashFile(commPath); mailSha=HashFile(mailPath); exportSha=HashFile(exportPath);
                    string comm=File.ReadAllText(commPath);
                    commSemantics=comm.Contains("DEFI_MATERIAU(ELAS=_F(E=210000") &&
                                  comm.Contains("FX=1000") &&
                                  comm.Contains("DX=0.0") && comm.Contains("DY=0.0") && comm.Contains("DZ=0.0") &&
                                  comm.Contains("MECA_STATIQUE") && comm.Contains("NOM_CHAM=('DEPL'") && comm.Contains("SIEQ_NOEU");
                    mailNonEmpty=mailBytes>0;
                    string exportText=File.ReadAllText(exportPath);
                    exportNonEmpty=exportBytes>0 && exportText.Contains("F comm astermax_c862_static.comm D 1") &&
                                   exportText.Contains("F libr astermax_c862_static.mail D 20") &&
                                   exportText.Contains("F rmed astermax_c862_static.rmed R 80");
                }

                qualified=unitBefore && pmxRoundtrip && studyGenerated && commSemantics && mailNonEmpty && exportNonEmpty && translationWarningsClean;
                if(!qualified) throw new InvalidOperationException("Code_Aster generation gate failed. Warnings: "+warningSummary);
            }
            catch(Exception ex) { error=ex.GetType().Name+": "+ex.Message; }

            WriteEvidence(evidencePath,workDir,pmxPath,sourceReady,unitBefore,pmxSaved,pmxReopened,unitAfter,
                          materialPersisted,sectionPersisted,stepPersisted,fixedPersisted,loadPersisted,valuesPersisted,
                          pmxRoundtrip,studyGenerated,commSemantics,mailNonEmpty,exportNonEmpty,translationWarningsClean,qualified,
                          persistedE,persistedF1,pmxBytes,commBytes,mailBytes,exportBytes,pmxSha,commSha,mailSha,exportSha,
                          commPath,mailPath,exportPath,warningSummary,error);
        }

        private static bool HasQualifiedSource(FeModel model)
        {
            if(model==null || model.Mesh==null || model.Mesh.Nodes.Count==0 || model.Mesh.Elements.Count==0) return false;
            if(!model.Materials.ContainsKey("AsterMax_Steel_Demo") || !model.Sections.ContainsKey("AsterMax_Solid_Section")) return false;
            StaticStep step=model.StepCollection.GetStep("Static_Structural") as StaticStep;
            return step!=null && step.BoundaryConditions.ContainsKey("Fixed_Support") && step.Loads.ContainsKey("Force_XMAX");
        }
        private static bool IsMmNMPa(UnitSystem u)
        {
            return u!=null && u.UnitSystemType==UnitSystemType.MM_TON_S_C &&
                   String.Equals(u.LengthUnitAbbreviation,"mm",StringComparison.OrdinalIgnoreCase) &&
                   String.Equals(u.ForceUnitAbbreviation,"N",StringComparison.OrdinalIgnoreCase) &&
                   String.Equals(u.PressureUnitAbbreviation,"MPa",StringComparison.OrdinalIgnoreCase);
        }
        private static bool Nearly(double a,double b){return !Double.IsNaN(a) && !Double.IsInfinity(a) && Math.Abs(a-b)<=Math.Max(1E-9,Math.Abs(b)*1E-12);}
        private static bool NonEmpty(string p){return !String.IsNullOrWhiteSpace(p) && File.Exists(p) && new FileInfo(p).Length>0;}
        private static string HashFile(string path)
        {
            using(SHA256 sha=SHA256.Create()) using(FileStream fs=File.OpenRead(path))
            { byte[] h=sha.ComputeHash(fs); StringBuilder sb=new StringBuilder(); foreach(byte b in h) sb.Append(b.ToString("x2",CultureInfo.InvariantCulture)); return sb.ToString(); }
        }
        private static string Num(double v){return Double.IsNaN(v)||Double.IsInfinity(v)?"null":v.ToString("R",CultureInfo.InvariantCulture);}
        private static string Json(string s){return "\""+(s??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r"," ").Replace("\n"," ")+"\"";}
        private static void WriteEvidence(string path,string workDir,string pmxPath,bool sourceReady,bool unitBefore,bool pmxSaved,bool pmxReopened,bool unitAfter,
            bool mat,bool sec,bool step,bool fixedBc,bool load,bool values,bool pmxRoundtrip,bool generated,bool commSemantics,bool mail,bool exportOk,bool warningsClean,bool qualified,
            double e,double f1,long pmxBytes,long commBytes,long mailBytes,long exportBytes,string pmxSha,string commSha,string mailSha,string exportSha,
            string commPath,string mailPath,string exportPath,string warnings,string error)
        {
            if(String.IsNullOrWhiteSpace(path)) return; string dir=Path.GetDirectoryName(path); if(!String.IsNullOrWhiteSpace(dir))Directory.CreateDirectory(dir);
            string j="{\n"+
                "  \"schema\": \"astermax.unit-pmx-codeaster-generation.v1\",\n"+
                "  \"source_structural_model_ready\": "+(sourceReady?"true":"false")+",\n"+
                "  \"unit_system_before_pmx_mm_n_mpa\": "+(unitBefore?"true":"false")+",\n"+
                "  \"native_save_to_pmx_nonzero\": "+(pmxSaved?"true":"false")+",\n"+
                "  \"native_open_pmx_roundtrip\": "+(pmxReopened?"true":"false")+",\n"+
                "  \"unit_system_after_pmx_mm_n_mpa\": "+(unitAfter?"true":"false")+",\n"+
                "  \"material_persisted\": "+(mat?"true":"false")+",\n"+
                "  \"solid_section_persisted\": "+(sec?"true":"false")+",\n"+
                "  \"static_step_persisted\": "+(step?"true":"false")+",\n"+
                "  \"fixed_support_persisted\": "+(fixedBc?"true":"false")+",\n"+
                "  \"force_load_persisted\": "+(load?"true":"false")+",\n"+
                "  \"persisted_E_mpa\": "+Num(e)+",\n  \"persisted_Fx_n\": "+Num(f1)+",\n"+
                "  \"dimensional_values_persisted\": "+(values?"true":"false")+",\n"+
                "  \"pmx_structural_roundtrip_qualified\": "+(pmxRoundtrip?"true":"false")+",\n"+
                "  \"codeaster_study_files_generated\": "+(generated?"true":"false")+",\n"+
                "  \"comm_unit_semantics_verified\": "+(commSemantics?"true":"false")+",\n"+
                "  \"mail_nonempty\": "+(mail?"true":"false")+",\n  \"export_contract_verified\": "+(exportOk?"true":"false")+",\n"+
                "  \"translation_warnings_clean\": "+(warningsClean?"true":"false")+",\n"+
                "  \"unit_pmx_codeaster_generation_qualified\": "+(qualified?"true":"false")+",\n"+
                "  \"pmx_bytes\": "+pmxBytes+",\n  \"comm_bytes\": "+commBytes+",\n  \"mail_bytes\": "+mailBytes+",\n  \"export_bytes\": "+exportBytes+",\n"+
                "  \"pmx_sha256\": "+Json(pmxSha)+",\n  \"comm_sha256\": "+Json(commSha)+",\n  \"mail_sha256\": "+Json(mailSha)+",\n  \"export_sha256\": "+Json(exportSha)+",\n"+
                "  \"pmx_path\": "+Json(pmxPath)+",\n  \"comm_path\": "+Json(commPath)+",\n  \"mail_path\": "+Json(mailPath)+",\n  \"export_path\": "+Json(exportPath)+",\n"+
                "  \"translation_warnings\": "+Json(warnings)+",\n"+
                "  \"solver_executed\": false,\n  \"solver_verified\": false,\n  \"industrial_validation\": false,\n  \"ansys_equivalence\": false,\n"+
                "  \"working_directory\": "+Json(workDir)+",\n  \"error\": "+Json(error)+"\n}";
            File.WriteAllText(path,j,Encoding.UTF8);
        }
    }
}
