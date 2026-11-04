using System;
using System.IO;
using System.Reflection;
using Newtonsoft.Json.Linq;
using PrePoMax;
public static class ContactLawTests {
 static int checks;
 static void Check(bool b,string m){if(!b)throw new Exception(m);checks++;}
 static JObject Fixture(){
  var t=typeof(AsterMaxC1207ContactTests);
  var p=(JObject)t.GetMethod("Pair",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{1,new[]{"A1","A2","A3"},new[]{"B1","B2","B3"}});
  return (JObject)t.GetMethod("Contract",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{new JArray(p)});
 }
 static void Reject(JObject c,string path){
  string before=c.ToString();
  try{AsterMaxCodeAsterNativeExporter.ExportContract(c,path,"law");throw new Exception("Unsupported law emitted");}
  catch(InvalidDataException){Check(!Directory.Exists(path),"output created before gate");Check(before==c.ToString(),"source mutated");}
 }
 public static JObject Run(string output){
  Directory.CreateDirectory(output);
  foreach(string law in new[]{"Tied","Linear","Exponential","Tabular","Unknown"}){
   var c=Fixture();c["contacts"][0]["normal_law"]=law;c["contacts"][0]["normal_stiffness_k"]=1234;c["contacts"][0]["friction_stick_slope"]=567;
   var reopened=JObject.Parse(c.ToString());Check(JToken.DeepEquals(c,reopened),"contract reopen changed law or coefficients");
   Reject(reopened,Path.Combine(output,law));
  }
  var missing=Fixture();((JObject)missing["contacts"][0]).Remove("normal_law");Reject(missing,Path.Combine(output,"missing"));
  foreach(double slope in new[]{10.0,0.0,-1.0,Double.PositiveInfinity}){
   var c=Fixture();c["contacts"][0]["friction_stick_slope"]=slope;Reject(c,Path.Combine(output,"slope"+checks));
  }
  foreach(double mu in new[]{0.0,-1.0,Double.NaN,Double.PositiveInfinity}){
   var c=Fixture();c["contacts"][0]["friction"]="COULOMB";c["contacts"][0]["friction_coefficient"]=mu;Reject(c,Path.Combine(output,"mu"+checks));
  }
  foreach(string key in new[]{"normal_law","formulation","friction","friction_coefficient"}) {
   foreach(JToken value in new JToken[]{JValue.CreateNull(),new JObject(),new JArray(),new JValue(true)}) {
    var c=Fixture();c["contacts"][0][key]=value;Reject(c,Path.Combine(output,"malformed"+checks));
   }
  }
  foreach(string key in new[]{"contact_init","law_schema","solver_route","normal_stiffness_usage"}) {
   var absent=Fixture();((JObject)absent["contacts"][0]).Remove(key);Reject(absent,Path.Combine(output,"absent"+checks));
   foreach(JToken value in new JToken[]{JValue.CreateNull(),new JObject(),new JArray(),new JValue(true),new JValue(1),new JValue("UNKNOWN"),new JValue("OUI'"),new JValue("OUI\n")}) {
    var c=Fixture();c["contacts"][0][key]=value;Reject(c,Path.Combine(output,"metadata"+checks));
   }
  }
  foreach(string key in new[]{"solver_route","normal_stiffness_usage","law_schema"}) {
   var c=Fixture();c["contacts"][0][key]=key=="solver_route"?"PENALISATION":key=="law_schema"?"astermax-contact-law/v2":"ACTIVE";
   Reject(c,Path.Combine(output,"contradiction"+checks));
  }
  foreach(string initial in new[]{"INTERPENETRE","OUI","NON"}) {
   var c=Fixture();c["contacts"][0]["contact_init"]=initial;string dir=Path.Combine(output,"init-"+initial);
   AsterMaxCodeAsterNativeExporter.ExportContract(c,dir,"law");
   Check(File.ReadAllText(Path.Combine(dir,"law.comm")).Contains("CONTACT_INIT='"+initial+"'"),"initial state not faithfully emitted");
  }
  foreach(string role in new[]{"master","slave"}) {
   foreach(string field in new[]{"group","face","node"}) {
    foreach(JToken bad in new JToken[]{JValue.CreateNull(),new JValue(123),new JValue("A'"),new JValue("A B"),new JValue("A\nFIN"),new JValue("A;B"),new JValue("ÁBC"),new JValue(new string('A',field=="group"?25:9))}) {
     var c=Fixture();var surface=c["contacts"][0][role];
     if(field=="group") surface["group"]=bad;else if(field=="face") surface["elements"][0]["id"]=bad;else surface["elements"][0]["nodes"][0]=bad;
     Reject(c,Path.Combine(output,"identifier"+checks));
    }
   }
  }
  var named=Fixture();named["contacts"][0]["master"]["source_surface"]="Nombre usuario ' con espacios";
  AsterMaxContactLaw.ValidateAll(named["contacts"]);
  Check((string)named["contacts"][0]["master"]["group"]=="AM_M001" && (string)named["contacts"][0]["slave"]["group"]=="AM_S001" &&
   (string)named["contacts"][0]["master"]["source_surface"]=="Nombre usuario ' con espacios","bridge identifiers/source metadata preserved");
  foreach(bool first in new[]{false,true}) {
   var c=Fixture();var bad=(JObject)c["contacts"][0].DeepClone();bad["name"]="Unsupported";bad["normal_law"]="Tied";
   if(first)((JArray)c["contacts"]).Insert(0,bad);else ((JArray)c["contacts"]).Add(bad);
   Reject(c,Path.Combine(output,"mixed"+checks));
  }
  var hardK=Fixture();hardK["contacts"][0]["normal_stiffness_k"]=1e7;
  AsterMaxContactLaw.Validate((JObject)hardK["contacts"][0]);Check(true,"Hard inactive K allowed");
  foreach(bool coulomb in new[]{false,true}){
   var c=Fixture();c["contacts"][0]["friction"]=coulomb?"COULOMB":"SANS";c["contacts"][0]["friction_coefficient"]=coulomb?0.3:0.0;
   var reopened=JObject.Parse(c.ToString());string path=Path.Combine(output,coulomb?"coulomb":"hard");
   AsterMaxCodeAsterNativeExporter.ExportContract(reopened,path,"law");string comm=File.ReadAllText(Path.Combine(path,"law.comm"));
   Check(comm.Contains("FORMULATION='CONTINUE'") && comm.Contains(coulomb?"FROTTEMENT='COULOMB'":"FROTTEMENT='SANS'"),"Hard script wrong route");
   Check(!comm.Contains("LIAISON_DDL"),"Hard converted to MPC");
   if(coulomb) Check(comm.Contains("COULOMB=0.3"),"friction coefficient missing");
  }
  var mixed=Fixture();var second=(JObject)mixed["contacts"][0].DeepClone();
  second["name"]="Coulomb zone";second["friction"]="COULOMB";second["friction_coefficient"]=0.2;
  // Separate node identities so topology is trivially satisfiable; reverse roles to avoid duplicate slave group names.
  second["master"]=mixed["contacts"][0]["slave"].DeepClone();second["slave"]=mixed["contacts"][0]["master"].DeepClone();
  ((JArray)mixed["contacts"]).Add(second);
  string mixedPath=Path.Combine(output,"mixed-supported");
  AsterMaxCodeAsterNativeExporter.ExportContract(mixed,mixedPath,"law");
  string mixedComm=File.ReadAllText(Path.Combine(mixedPath,"law.comm"));
  Check(mixedComm.Contains("COULOMB=0.2") && mixedComm.Contains("COULOMB=0)"),"mixed SANS zero/Coulomb coefficients lost");
  var invalid=Fixture();invalid["contacts"][0]["normal_law"]="Tied";
  string oldPath=Path.Combine(output,"existing-output");Directory.CreateDirectory(oldPath);File.WriteAllText(Path.Combine(oldPath,"law.comm"),"OLD_NOT_NEW");
  try { AsterMaxCodeAsterNativeExporter.ExportContract(invalid,oldPath,"law");throw new Exception("invalid accepted"); }
  catch(InvalidDataException) {Check(File.ReadAllText(Path.Combine(oldPath,"law.comm"))=="OLD_NOT_NEW" && Directory.GetFiles(oldPath).Length==1,"invalid law overwrote existing artifacts");}
  return new JObject{["status"]="PASS",["checks"]=checks,["roundtrip"]="JSON_CONTRACT_ONLY",["solver"]="NOT_RUN",["native_pmx"]="NOT_RUN"};
 }
}
