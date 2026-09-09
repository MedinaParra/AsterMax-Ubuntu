param([string]$Root)
$ErrorActionPreference='Stop'

$vtk=Join-Path $Root 'vtkControl/vtkControl.cs'
$binding=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $vtk)){throw 'vtkControl source missing.'}
if(!(Test-Path $binding)){throw 'C9.71 results binding must be applied before C9.72.'}

# C9.72 truth boundary: export the pixels owned by vtkRenderWindow itself. Do not use
# WinForms DrawToBitmap, screen-copy APIs, or a reconstructed/mock image.
$v=Get-Content $vtk -Raw
$anchor='        public void SwithchLights()'
$method=@'
        // AsterMax C9.72: native renderer evidence. This captures the vtkRenderWindow
        // framebuffer after an explicit render, including actors, scalar bar and VTK widgets.
        public void SaveNativeFramebufferPng(string fileName)
        {
            if (String.IsNullOrWhiteSpace(fileName)) throw new ArgumentException("PNG path is required.", "fileName");
            string directory = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(fileName));
            if (!System.IO.Directory.Exists(directory)) System.IO.Directory.CreateDirectory(directory);

            RenderSceene();
            vtkWindowToImageFilter windowToImage = vtkWindowToImageFilter.New();
            vtkPNGWriter pngWriter = vtkPNGWriter.New();
            try
            {
                windowToImage.SetInput(_renderWindow);
                windowToImage.SetInputBufferTypeToRGB();
                windowToImage.ReadFrontBufferOff();
                windowToImage.Update();
                pngWriter.SetInputConnection(windowToImage.GetOutputPort());
                pngWriter.SetFileName(fileName);
                pngWriter.Write();
            }
            finally
            {
                pngWriter.Dispose();
                windowToImage.Dispose();
            }
            if (!System.IO.File.Exists(fileName) || new System.IO.FileInfo(fileName).Length == 0)
                throw new InvalidOperationException("VTK framebuffer PNG was not written.");
        }

'@
if(-not $v.Contains($anchor)){throw 'C9.72 vtkControl insertion anchor missing.'}
$v=$v.Replace($anchor,$method+$anchor)
Set-Content $vtk $v -Encoding UTF8

$b=Get-Content $binding -Raw
$summaryAnchor='        public string RendererContractSummary()'
$methods=@'
        public void CaptureNativeFramebuffer(string fileName)
        {
            if(_scene==null) RefreshMetadata();
            if(_scene.FeaValuesInvented) throw new InvalidOperationException("Synthetic FEA scene rejected by framebuffer evidence capture.");
            if(_view==null) throw new InvalidOperationException("VTK results viewport is not initialized.");
            _view.SaveNativeFramebufferPng(fileName);
        }

        public string NativeFramebufferEvidenceContract()
        {
            RefreshMetadata();
            return String.Format(System.Globalization.CultureInfo.InvariantCulture,
                "source=vtkRenderWindow|field={0}|unit={1}|min={2:R}|max={3:R}|invented=false",
                _scene.Field,_scene.Unit,_scene.MinValue,_scene.MaxValue);
        }

'@
if(-not $b.Contains($summaryAnchor)){throw 'C9.72 AsterMax renderer summary anchor missing.'}
$b=$b.Replace($summaryAnchor,$methods+$summaryAnchor)
Set-Content $binding $b -Encoding UTF8

Write-Host 'C9.72 native vtkRenderWindow framebuffer evidence capture injected.' -ForegroundColor Green
