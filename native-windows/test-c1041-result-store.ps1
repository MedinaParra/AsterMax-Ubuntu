param([string]$BuildRoot,[string]$OutDir)
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force $OutDir | Out-Null
$json=Get-ChildItem $BuildRoot -Recurse -Filter Newtonsoft.Json.dll |
    Where-Object {$_.FullName -match 'bin\\x64\\Release'} | Select-Object -First 1
if(-not $json){ throw 'Result-store tests require the real build Newtonsoft.Json.dll.' }
[Reflection.Assembly]::LoadFrom($json.FullName) | Out-Null
$store=Get-Content (Join-Path $PSScriptRoot 'AsterMaxProjectResultsStore.cs') -Raw
$store=$store.Substring(0,$store.IndexOf('    public partial class FrmMain'))+"`n}"
$fixture=@'
using System;
using System.IO;
using Newtonsoft.Json.Linq;
namespace PrePoMax {
    // Unit stand-in: tests file persistence/identity, not FEA array interpretation.
    internal sealed class AsterMaxResultsBundle {
        public string SourceFile { get; set; }
        public string ResultModelFingerprintSha256 { get; set; }
        public static AsterMaxResultsBundle Load(string path) {
            var data=JObject.Parse(File.ReadAllText(path));
            return new AsterMaxResultsBundle { SourceFile=path,
                ResultModelFingerprintSha256=(string)data["integrity"]["model_fingerprint_sha256"] };
        }
    }
    public static class ResultStoreFixtureTests {
        static int count;
        static void Check(bool condition,string message) {
            if(!condition) throw new Exception(message);
            count++;
        }
        static void Rejected(Action action,string message) {
            bool blocked=false;
            try { action(); } catch(InvalidDataException) { blocked=true; } catch(IOException) { blocked=true; }
            Check(blocked,message);
        }
        public static int Run(string directory) {
            string original=Path.Combine(directory,"original");Directory.CreateDirectory(original);
            string project=Path.Combine(original,"model.pmx");File.WriteAllText(project,"unit-fixture");
            string source=Path.Combine(original,"source.json");string fp=new string('a',64);
            File.WriteAllText(source,new JObject { ["integrity"]=new JObject { ["model_fingerprint_sha256"]=fp } }.ToString());
            string qualification=Path.Combine(original,"mechanical-qualification.json");
            File.WriteAllText(qualification,new JObject {
                ["bundle_sha256"]=AsterMaxProjectResultsStore.Hash(source),
                ["engineering_qualification"]="SOLVED_WITH_ENGINEERING_WARNINGS",
                ["findings"]=new JArray()
            }.ToString());
            var input=AsterMaxResultsBundle.Load(source);
            AsterMaxProjectResultsStore.Save(project,input,fp,null,null);
            var loaded=AsterMaxProjectResultsStore.Load(project,fp);
            Check(File.ReadAllText(loaded.SourceFile)==File.ReadAllText(source),"Snapshot changed bundle bytes.");
            Rejected(() => AsterMaxProjectResultsStore.Load(project,new string('b',64)),"Stale model accepted.");
            string moved=Path.Combine(directory,"moved");Directory.Move(original,moved);
            project=Path.Combine(moved,"model.pmx");
            loaded=AsterMaxProjectResultsStore.Load(project,fp);
            Check(loaded.SourceFile.StartsWith(moved),"Relative snapshot failed after moving the project.");
            File.AppendAllText(loaded.SourceFile," ");
            Rejected(() => AsterMaxProjectResultsStore.Load(project,fp),"Tampered bundle accepted.");
            string manifest=AsterMaxProjectResultsStore.ManifestPath(project);
            var data=JObject.Parse(File.ReadAllText(manifest));
            data["result_directory"]=".."+Path.DirectorySeparatorChar+".."+Path.DirectorySeparatorChar+"escape";
            File.WriteAllText(manifest,data.ToString());
            Rejected(() => AsterMaxProjectResultsStore.Load(project,fp),"Escaping result path accepted.");
            AsterMaxProjectResultsStore.SaveEmpty(project,"STALE");
            Check(AsterMaxProjectResultsStore.Load(project,fp)==null,"Stale pointer restored old results.");
            AsterMaxProjectResultsStore.SaveEmpty(project,"NONE");
            Check(AsterMaxProjectResultsStore.Load(project,fp)==null,"Empty project restored old results.");
            return count;
        }
    }
}
'@
$qualification=Get-Content (Join-Path $PSScriptRoot 'AsterMaxMechanicalQualification.cs') -Raw
$files=@()
foreach($entry in @(@('store.cs',$store),@('qualification.cs',$qualification),@('fixture.cs',$fixture))){
    $path=Join-Path $OutDir $entry[0]
    Set-Content $path $entry[1] -Encoding UTF8
    $files+=$path
}
Add-Type -Path $files -ReferencedAssemblies @($json.FullName,'System.Core.dll')
$count=[PrePoMax.ResultStoreFixtureTests]::Run((Join-Path $OutDir 'cases'))
@{status='PASS';cases=$count;scope='UNIT_FILE_PERSISTENCE';solver_execution='NOT_RUN';synthetic_fixture_only=$true} |
    ConvertTo-Json | Set-Content (Join-Path $OutDir 'result-store-fixtures.json') -Encoding UTF8
Write-Host "C1041_RESULT_STORE_FIXTURES=PASS cases=$count (not FEA or GUI certification)"
