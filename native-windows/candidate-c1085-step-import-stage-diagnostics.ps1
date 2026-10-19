param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.85 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

# Instrument the proven failing serial ImportBrepPartFile path. Do not change
# geometry semantics: identify whether FormatException occurs before NetGen,
# during NetGen submission, or while parsing the generated VIS file.
$argAnchor='                _form.WriteDataToOutput("AsterMax CAD tessellation START: " + Path.GetFileName(brepFileName) +'
if(!$c.Contains($argAnchor)){throw 'C10.85 tessellation START anchor missing.'}
$c=$c.Replace($argAnchor,'                _form.WriteDataToOutput("ASTERMAX_CAD_STAGE=ARG_READY culture=" + System.Globalization.CultureInfo.CurrentCulture.Name + " ui=" + System.Globalization.CultureInfo.CurrentUICulture.Name + " job=" + jobName);'+"`n"+$argAnchor)

$submit='                _netgenJob.Submit();'
if(!$c.Contains($submit)){throw 'C10.85 NetGen Submit anchor missing.'}
$c=$c.Replace($submit,'                _form.WriteDataToOutput("ASTERMAX_CAD_STAGE=NETGEN_SUBMIT job=" + jobName);'+"`n"+$submit+"`n"+'                _form.WriteDataToOutput("ASTERMAX_CAD_STAGE=NETGEN_RETURN status=" + _netgenJob.JobStatus.ToString() + " job=" + jobName);')

$parse='                string[] addedPartNames = _model.ImportGeometryFromBrepFile(visFileName, brepFileName);'
if(!$c.Contains($parse)){throw 'C10.85 VIS parser anchor missing.'}
$parseReplacement=@'
                _form.WriteDataToOutput("ASTERMAX_CAD_STAGE=VIS_PARSE_START bytes=" + visualizationBytes + " vis=" + Path.GetFileName(visFileName));
                string[] addedPartNames;
                try
                {
                    addedPartNames = _model.ImportGeometryFromBrepFile(visFileName, brepFileName);
                }
                catch (FormatException ex)
                {
                    string diagnostic = "ASTERMAX_CAD_FORMAT_EXCEPTION stage=VIS_PARSE culture=" +
                                        System.Globalization.CultureInfo.CurrentCulture.Name +
                                        " ui=" + System.Globalization.CultureInfo.CurrentUICulture.Name +
                                        " bytes=" + visualizationBytes +
                                        " vis=" + Path.GetFileName(visFileName) +
                                        " message=" + ex.Message +
                                        " stack=" + ex.StackTrace;
                    _form.WriteDataToOutput(diagnostic);
                    _errors.Add(diagnostic);
                    return null;
                }
                _form.WriteDataToOutput("ASTERMAX_CAD_STAGE=VIS_PARSE_PASS parts=" + (addedPartNames == null ? 0 : addedPartNames.Length));
'@
$c=$c.Replace($parse,$parseReplacement.TrimEnd())
Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.85: STEP/VIS stage diagnostics applied without changing import geometry semantics.' -ForegroundColor Green
