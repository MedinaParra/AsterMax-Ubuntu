param([string]$Root)
$ErrorActionPreference='Stop'

# 1) Harden ModelTree startup: replace blind Nodes.Find(...)[0] lookups with validated lookup.
$modelTree = Join-Path $Root 'UserControls/ModelTree.cs'
$t = Get-Content $modelTree -Raw

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

# 2) Re-align VTK after AsterMax adds its title/ribbon chrome after the native Shown layout.
$ui = Join-Path $Root 'PrePoMax/FrmMain.AsterMaxNativeUi.cs'
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

Write-Host 'C9.92 startup + viewport hardening applied.' -ForegroundColor Green
