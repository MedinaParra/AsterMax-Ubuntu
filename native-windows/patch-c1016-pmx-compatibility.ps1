param([string]$Root)
$ErrorActionPreference='Stop'

$tools=Join-Path $Root 'CaeGlobals/Tools.cs'
if(!(Test-Path $tools)){throw 'C10.16 requires CaeGlobals/Tools.cs.'}
$s=Get-Content $tools -Raw

# PMX embeds BinaryFormatter assembly identities. AsterMax intentionally keeps the
# PrePoMax namespaces/types but renamed the executable assembly to "AsterMax Mechanical".
# Map serialized type names to the currently loaded assembly that actually owns the type,
# so PMX files remain readable across the PrePoMax -> AsterMax identity transition and
# across AsterMax hotfix builds.
if(-not $s.Contains('internal sealed class AsterMaxCompatibleSerializationBinder')) {
    $nsAnchor='namespace CaeGlobals'+[Environment]::NewLine+'{'
    if(-not $s.Contains($nsAnchor)){throw 'C10.16 CaeGlobals namespace anchor missing.'}
    $binder=@'
namespace CaeGlobals
{
    internal sealed class AsterMaxCompatibleSerializationBinder : System.Runtime.Serialization.SerializationBinder
    {
        public override Type BindToType(string assemblyName, string typeName)
        {
            // First resolve by full serialized identity when it is still available.
            Type type=Type.GetType(typeName+", "+assemblyName,false);
            if(type!=null) return type;

            // Assembly identity may have changed (PrePoMax -> AsterMax Mechanical),
            // while namespaces and serializable type contracts remain intentionally intact.
            foreach(System.Reflection.Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    type=assembly.GetType(typeName,false,false);
                    if(type!=null) return type;
                }
                catch { }
            }

            // Last chance: load the simple assembly name and query the type.
            try
            {
                string simple=(assemblyName??"").Split(',')[0].Trim();
                if(simple.Length>0)
                {
                    System.Reflection.Assembly assembly=System.Reflection.Assembly.Load(simple);
                    if(assembly!=null)
                    {
                        type=assembly.GetType(typeName,false,false);
                        if(type!=null) return type;
                    }
                }
            }
            catch { }
            throw new System.Runtime.Serialization.SerializationException(
                "AsterMax PMX compatibility loader could not resolve serialized type '"+typeName+"' from assembly '"+assemblyName+"'.");
        }
    }
'@
    $s=$s.Replace($nsAnchor,$binder.TrimEnd())
}

# Apply the compatibility binder to both PMX dump-load entry points in Tools.cs.
$formatter='                BinaryFormatter formatter = new BinaryFormatter();'
$formatterWithBinder=$formatter+[Environment]::NewLine+'                formatter.Binder = new AsterMaxCompatibleSerializationBinder();'+[Environment]::NewLine+'                formatter.AssemblyFormat = System.Runtime.Serialization.Formatters.FormatterAssemblyStyle.Simple;'
$count=([regex]::Matches($s,[regex]::Escape($formatter))).Count
if($count -lt 2 -and -not $s.Contains('formatter.Binder = new AsterMaxCompatibleSerializationBinder();')){throw 'C10.16 expected BinaryFormatter load anchors were not found.'}
# Tools.cs only contains deserialization formatters in this pinned upstream, so patch all occurrences there.
if(-not $s.Contains('formatter.Binder = new AsterMaxCompatibleSerializationBinder();')){$s=$s.Replace($formatter,$formatterWithBinder)}

foreach($token in @('AsterMaxCompatibleSerializationBinder','AppDomain.CurrentDomain.GetAssemblies()','formatter.Binder = new AsterMaxCompatibleSerializationBinder()','FormatterAssemblyStyle.Simple')){
    if(-not $s.Contains($token)){throw "C10.16 PMX compatibility token missing: $token"}
}
Set-Content $tools $s -Encoding UTF8

# Future saves use the simple assembly format as well, reducing unnecessary version coupling.
$ext=Join-Path $Root 'CaeGlobals/Extensions.cs'
if(!(Test-Path $ext)){throw 'C10.16 requires CaeGlobals/Extensions.cs.'}
$e=Get-Content $ext -Raw
$saveFormatter='                BinaryFormatter formatter = new BinaryFormatter();'
$saveNew=$saveFormatter+[Environment]::NewLine+'                formatter.AssemblyFormat = System.Runtime.Serialization.Formatters.FormatterAssemblyStyle.Simple;'
if(-not $e.Contains('FormatterAssemblyStyle.Simple')){$e=$e.Replace($saveFormatter,$saveNew)}
Set-Content $ext $e -Encoding UTF8

Write-Host 'C10.16 PMX compatibility binder + simple assembly serialization applied.' -ForegroundColor Green
