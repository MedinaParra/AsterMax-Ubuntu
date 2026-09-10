param([string]$Root)
$ErrorActionPreference='Stop'

# 1) Restore stable internal ModelTree keys. Presentation text must never replace the
# persistent TreeNode.Name contract used by ModelTree's constructor and command routing.
$modelTree = Join-Path $Root 'UserControls/ModelTree.cs'
$t = Get-Content $modelTree -Raw
$t = $t.Replace('private string _geomPartsName = "Geometry";','private string _geomPartsName = "Parts";')
$t = $t.Replace('private string _meshingParametersName = "Mesh Controls";','private string _meshingParametersName = "Meshing Parameters";')
$t = $t.Replace('private string _meshRefinementsName = "Local Mesh Controls";','private string _meshRefinementsName = "Mesh Refinements";')
$t = $t.Replace('private string _boundaryConditionsName = "Supports / BCs";','private string _boundaryConditionsName = "BCs";')
$t = $t.Replace('private string _analysesName = "Solution";','private string _analysesName = "Analyses";')

# Harden all static tree lookups so future designer/key drift reports the missing node explicitly
# instead of throwing IndexOutOfRangeException from Nodes.Find(...)[0].
$ctorMarker = '        // Constructors                                                                                                             '
if(-not $t.Contains('private TreeNode RequireTreeNode(')) {
$helper = @'
        private TreeNode RequireTreeNode(CodersLabTreeView tree, string expectedName)
        {
            if (tree == null) throw new InvalidOperationException("ModelTree control is not initialized: " + expectedName);
            TreeNode[] byName = tree.Nodes.Find(expectedName, true);
            if (byName != null && byName.Length > 0) return byName[0];
            foreach (TreeNode root in tree.Nodes)
            {
                TreeNode found = FindTreeNodeByText(root, expectedName);
                if (found != null) return found;
            }
            throw new InvalidOperationException("Required ModelTree node not found: '" + expectedName + "'.");
        }

        private TreeNode FindTreeNodeByText(TreeNode node, string expectedText)
        {
            if (node == null) return null;
            if (string.Equals(node.Text, expectedText, StringComparison.OrdinalIgnoreCase)) return node;
            foreach (TreeNode child in node.Nodes)
            {
                TreeNode found = FindTreeNodeByText(child, expectedText);
                if (found != null) return found;
            }
            return null;
        }

'@
    if(-not $t.Contains($ctorMarker)){ throw 'ModelTree constructor marker not found' }
    $t = $t.Replace($ctorMarker, $helper + $ctorMarker)
}
$t = [regex]::Replace($t, '([A-Za-z0-9_]+)\.Nodes\.Find\((_[A-Za-z0-9_]+), true\)\[0\]', 'RequireTreeNode($1, $2)')
Set-Content $modelTree $t -Encoding UTF8

# 2) Re-align VTK after AsterMax adds title/ribbon chrome after the native Shown layout.
# Native FrmMain_Shown calculates VTK bounds before our AsterMax chrome exists; recalculate once
# the custom chrome has changed the client area.
$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(Test-Path $ui) {
    $u = Get-Content $ui -Raw
    $old = @'
            finally
            {
                ResumeLayout(true);
                PerformLayout();
            }
'@
    $new = @'
            finally
            {
                ResumeLayout(true);
                PerformLayout();
                BeginInvoke(new Action(() =>
                {
                    if (IsDisposed || _vtk == null) return;
                    PerformLayout();
                    UpdateVtkControlSize();
                    _vtk.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Bottom;
                    _vtk.BringToFront();
                    var badge = splitContainer1.Panel2.Controls["asterMaxGraphicsBadge"];
                    if (badge != null) badge.BringToFront();
                    splitContainer1.Panel2.PerformLayout();
                    _vtk.Invalidate();
                }));
            }
'@
    if(-not $u.Contains($old)){ throw 'AsterMax UI finally block anchor not found' }
    $u = $u.Replace($old,$new)
    Set-Content $ui $u -Encoding UTF8
} else {
    throw 'AsterMax native UI partial not found; apply patch-astermax.ps1 before C9.92'
}

# 3) Clean-install workspace repair. STEP/CAD import requires a valid work directory even before
# any solver execution. Delegate to the dedicated C9.99 patch so the workspace policy stays isolated.
$self = Split-Path -Parent $MyInvocation.MyCommand.Path
$c999 = Join-Path $self 'patch-c999-portable-workspace-step.ps1'
if(-not (Test-Path $c999)){ throw 'C9.99 portable workspace patch missing' }
& $c999 -Root $Root

Write-Host 'C9.99 ModelTree + viewport + portable workspace hardening applied.' -ForegroundColor Green
