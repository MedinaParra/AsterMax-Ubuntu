param([string]$Root)
$ErrorActionPreference='Stop'

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")

# C10.25 uses original AsterMax engineering pictograms drawn with GDI+.
# Mechanical-inspired visual language, but original AsterMax artwork.

$cmdStart = $u.IndexOf('        private Button CommandTile(')
$cmdEnd = $u.IndexOf('        private Label InfoCard(', $cmdStart)
if($cmdStart -lt 0 -or $cmdEnd -lt 0) { throw 'C10.25 CommandTile method anchors missing.' }
$cmd = $u.Substring($cmdStart, $cmdEnd-$cmdStart)

if(-not $cmd.Contains('CreateAsterMaxRibbonIcon(text, group, primary)'))
{
    $heightPattern = '(?m)^(?<i>\s*)Height\s*=\s*\d+,\s*$'
    $hm = [regex]::Match($cmd, $heightPattern)
    if(-not $hm.Success) { throw 'C10.25 CommandTile height anchor missing.' }
    $i = $hm.Groups['i'].Value
    $insert = $i + 'Height = 82,' + "`n" +
              $i + 'Image = CreateAsterMaxRibbonIcon(text, group, primary),' + "`n" +
              $i + 'ImageAlign = ContentAlignment.TopCenter,' + "`n" +
              $i + 'TextImageRelation = TextImageRelation.ImageAboveText,'
    $cmd = $cmd.Substring(0,$hm.Index) + $insert + $cmd.Substring($hm.Index+$hm.Length)
}

$paddingPattern = '(?m)^(?<i>\s*)Padding\s*=\s*new Padding\([^\r\n]+\),\s*$'
$pm = [regex]::Match($cmd, $paddingPattern)
if(-not $pm.Success) { throw 'C10.25 CommandTile padding anchor missing.' }
$cmd = $cmd.Substring(0,$pm.Index) + $pm.Groups['i'].Value + 'Padding = new Padding(4, 5, 4, 3),' + $cmd.Substring($pm.Index+$pm.Length)

$fontPattern = '(?m)^(?<i>\s*)Font\s*=\s*new Font\("Segoe UI(?: Semibold)?",\s*[0-9.]+f[^\r\n]*$'
$fm = [regex]::Match($cmd, $fontPattern)
if(-not $fm.Success) { throw 'C10.25 CommandTile font anchor missing.' }
$cmd = $cmd.Substring(0,$fm.Index) + $fm.Groups['i'].Value + 'Font = new Font("Segoe UI Semibold", 8.0f)' + $cmd.Substring($fm.Index+$fm.Length)

$u = $u.Substring(0,$cmdStart) + $cmd + $u.Substring($cmdEnd)

$helperAnchor = '        private Label InfoCard(string text)'
$helpers = @'
        private Image CreateAsterMaxRibbonIcon(string text, string group, bool primary)
        {
            const int s = 32;
            var bmp = new Bitmap(s, s);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);

                var dark = Color.FromArgb(58, 64, 72);
                var muted = Color.FromArgb(112, 121, 132);
                var amber = Color.FromArgb(242, 181, 30);
                var fill = primary ? Color.FromArgb(255, 246, 218) : Color.FromArgb(247, 248, 250);

                using (var bg = new SolidBrush(fill))
                    g.FillEllipse(bg, 1, 1, 30, 30);
                using (var ring = new Pen(primary ? amber : Color.FromArgb(205, 211, 218), 1.2f))
                    g.DrawEllipse(ring, 1.5f, 1.5f, 29, 29);

                using (var p = new Pen(dark, 1.8f))
                using (var p2 = new Pen(amber, 2.2f))
                using (var pm = new Pen(muted, 1.3f))
                {
                    p.StartCap = p.EndCap = System.Drawing.Drawing2D.LineCap.Round;
                    p2.StartCap = p2.EndCap = System.Drawing.Drawing2D.LineCap.Round;
                    pm.StartCap = pm.EndCap = System.Drawing.Drawing2D.LineCap.Round;

                    string k = ((group ?? "") + "|" + (text ?? "")).ToLowerInvariant();

                    if (k.Contains("nuevo"))
                    {
                        g.DrawRectangle(p, 9, 7, 12, 17);
                        g.DrawLine(pm, 12, 11, 18, 11);
                        g.DrawLine(p2, 22, 18, 29, 18);
                        g.DrawLine(p2, 25.5f, 14.5f, 25.5f, 21.5f);
                    }
                    else if (k.Contains("abrir"))
                    {
                        g.DrawRectangle(p, 6, 10, 20, 13);
                        g.DrawLine(p, 6, 10, 12, 10);
                        g.DrawLine(p, 9, 7, 16, 7);
                        g.DrawLine(p, 16, 7, 19, 10);
                        g.DrawLine(p2, 13, 18, 23, 18);
                        g.DrawLine(p2, 20, 15, 23, 18);
                        g.DrawLine(p2, 20, 21, 23, 18);
                    }
                    else if (k.Contains("guardar"))
                    {
                        g.DrawRectangle(p, 7, 6, 18, 20);
                        g.DrawRectangle(pm, 11, 7, 9, 6);
                        g.DrawRectangle(p, 11, 17, 10, 7);
                        g.DrawLine(p2, 13, 20, 19, 20);
                    }
                    else if (k.Contains("importar"))
                    {
                        g.DrawRectangle(p, 6, 9, 17, 15);
                        g.DrawLine(p2, 17, 5, 17, 17);
                        g.DrawLine(p2, 13, 13, 17, 17);
                        g.DrawLine(p2, 21, 13, 17, 17);
                    }
                    else if (k.Contains("deshacer") || k.Contains("rehacer"))
                    {
                        bool redo = k.Contains("rehacer");
                        var r = new RectangleF(7, 8, 18, 15);
                        g.DrawArc(p, r, redo ? 205 : -25, 245);
                        if (redo)
                        {
                            g.DrawLine(p2, 23, 8, 27, 11);
                            g.DrawLine(p2, 23, 8, 20, 12);
                        }
                        else
                        {
                            g.DrawLine(p2, 9, 8, 5, 11);
                            g.DrawLine(p2, 9, 8, 12, 12);
                        }
                    }
                    else if (k.Contains("ajustar"))
                    {
                        g.DrawRectangle(p, 9, 9, 14, 14);
                        g.DrawLine(p2, 5, 10, 10, 10); g.DrawLine(p2, 6, 8, 5, 10); g.DrawLine(p2, 6, 12, 5, 10);
                        g.DrawLine(p2, 27, 22, 22, 22); g.DrawLine(p2, 26, 20, 27, 22); g.DrawLine(p2, 26, 24, 27, 22);
                        g.DrawLine(pm, 10, 5, 10, 10); g.DrawLine(pm, 8, 6, 10, 5); g.DrawLine(pm, 12, 6, 10, 5);
                        g.DrawLine(pm, 22, 27, 22, 22); g.DrawLine(pm, 20, 26, 22, 27); g.DrawLine(pm, 24, 26, 22, 27);
                    }
                    else if (k.Contains("isométr"))
                    {
                        AsterMaxDrawCube(g, p, p2, 16, 16, 9);
                    }
                    else if (k.Contains("analizar"))
                    {
                        g.DrawEllipse(p, 7, 7, 12, 12);
                        g.DrawLine(p2, 17, 17, 25, 25);
                        g.DrawLine(pm, 10, 13, 16, 13);
                    }
                    else if (k.Contains("material"))
                    {
                        g.DrawEllipse(p, 7, 7, 18, 18);
                        g.DrawArc(p2, 10, 10, 12, 12, 35, 150);
                        g.DrawLine(pm, 11, 20, 21, 12);
                    }
                    else if (k.Contains("sección"))
                    {
                        g.DrawLine(p, 9, 7, 23, 7);
                        g.DrawLine(p, 16, 7, 16, 25);
                        g.DrawLine(p, 9, 25, 23, 25);
                        g.DrawLine(p2, 12, 11, 20, 11);
                    }
                    else if (k.Contains("refinamiento"))
                    {
                        AsterMaxDrawMeshIcon(g, p, pm, 7, 7, 18, 18);
                        g.DrawRectangle(p2, 15, 15, 9, 9);
                        g.DrawLine(p2, 19.5f, 15, 19.5f, 24);
                        g.DrawLine(p2, 15, 19.5f, 24, 19.5f);
                    }
                    else if (k.Contains("malla") || k.Contains("controles"))
                    {
                        AsterMaxDrawMeshIcon(g, p, p2, 7, 7, 18, 18);
                    }
                    else if (k.Contains("paso"))
                    {
                        g.DrawEllipse(p, 7, 7, 18, 18);
                        g.DrawLine(p, 16, 16, 16, 10);
                        g.DrawLine(p2, 16, 16, 21, 19);
                    }
                    else if (k.Contains("apoyo"))
                    {
                        g.DrawLine(p, 7, 23, 25, 23);
                        g.DrawLine(pm, 9, 26, 13, 23); g.DrawLine(pm, 15, 26, 19, 23); g.DrawLine(pm, 21, 26, 25, 23);
                        g.DrawPolygon(p, new PointF[] { new PointF(16,8), new PointF(9,22), new PointF(23,22) });
                        g.DrawLine(p2, 16, 6, 16, 12);
                    }
                    else if (k.Contains("carga"))
                    {
                        g.DrawLine(p2, 16, 5, 16, 22);
                        g.DrawLine(p2, 11, 17, 16, 22);
                        g.DrawLine(p2, 21, 17, 16, 22);
                        g.DrawLine(p, 8, 25, 24, 25);
                    }
                    else if (k.Contains("verificar"))
                    {
                        g.DrawEllipse(p, 6, 6, 20, 20);
                        g.DrawLine(p2, 10, 16, 14, 20);
                        g.DrawLine(p2, 14, 20, 23, 11);
                    }
                    else if (k.Contains("ejecutar"))
                    {
                        g.DrawEllipse(p, 6, 6, 20, 20);
                        using (var b = new SolidBrush(amber))
                            g.FillPolygon(b, new PointF[] { new PointF(14,11), new PointF(22,16), new PointF(14,21) });
                    }
                    else if (k.Contains("monitor"))
                    {
                        g.DrawRectangle(p, 6, 7, 20, 16);
                        g.DrawLine(pm, 10, 26, 22, 26);
                        g.DrawLines(p2, new PointF[] { new PointF(9,18), new PointF(13,14), new PointF(16,17), new PointF(21,11), new PointF(24,14) });
                    }
                    else if (k.Contains("análisis"))
                    {
                        g.DrawEllipse(p, 7, 7, 18, 18);
                        g.DrawLine(pm, 16, 5, 16, 9);
                        g.DrawLine(pm, 16, 23, 16, 27);
                        g.DrawLine(pm, 5, 16, 9, 16);
                        g.DrawLine(pm, 23, 16, 27, 16);
                        g.DrawEllipse(p2, 12, 12, 8, 8);
                    }
                    else if (k.Contains("contornos"))
                    {
                        g.DrawRectangle(p, 7, 7, 18, 18);
                        g.DrawArc(pm, 9, 9, 14, 14, 20, 130);
                        g.DrawArc(p2, 11, 11, 10, 10, 200, 140);
                        g.DrawArc(p, 13, 13, 6, 6, 20, 180);
                    }
                    else if (k.Contains("deformada"))
                    {
                        g.DrawLine(pm, 6, 22, 26, 22);
                        g.DrawBezier(p2, new PointF(7,20), new PointF(11,6), new PointF(21,28), new PointF(25,10));
                    }
                    else if (k.Contains("original"))
                    {
                        g.DrawRectangle(p, 8, 8, 16, 16);
                        g.DrawRectangle(p2, 11, 11, 10, 10);
                    }
                    else if (k.Contains("frontal"))
                    {
                        AsterMaxDrawViewFace(g, p, p2, "F");
                    }
                    else if (k.Contains("superior"))
                    {
                        AsterMaxDrawViewFace(g, p, p2, "T");
                    }
                    else if (k.Contains("derecha"))
                    {
                        AsterMaxDrawViewFace(g, p, p2, "R");
                    }
                    else if (k.Contains("alámbrico"))
                    {
                        AsterMaxDrawCube(g, p, pm, 16, 16, 9);
                        g.DrawLine(p2, 10, 11, 22, 21);
                    }
                    else if (k.Contains("sin aristas"))
                    {
                        using (var b = new SolidBrush(Color.FromArgb(90, amber)))
                            g.FillRectangle(b, 9, 9, 14, 14);
                        g.DrawRectangle(p, 9, 9, 14, 14);
                    }
                    else if (k.Contains("aristas"))
                    {
                        AsterMaxDrawCube(g, p, p2, 16, 16, 9);
                    }
                    else if (k.Contains("resultados") || k.Contains("abrir"))
                    {
                        g.DrawRectangle(p, 7, 7, 18, 18);
                        g.DrawLine(pm, 10, 11, 22, 11);
                        g.DrawLine(p2, 10, 16, 22, 16);
                        g.DrawLine(pm, 10, 21, 22, 21);
                    }
                    else
                    {
                        AsterMaxDrawCube(g, p, p2, 16, 16, 8);
                    }
                }
            }
            return bmp;
        }

        private void AsterMaxDrawMeshIcon(Graphics g, Pen p, Pen accent, int x, int y, int w, int h)
        {
            g.DrawRectangle(p, x, y, w, h);
            for (int i = 1; i < 3; i++)
            {
                float xx = x + w * i / 3f;
                float yy = y + h * i / 3f;
                g.DrawLine(i == 2 ? accent : p, xx, y, xx, y + h);
                g.DrawLine(i == 2 ? accent : p, x, yy, x + w, yy);
            }
        }

        private void AsterMaxDrawCube(Graphics g, Pen p, Pen accent, float cx, float cy, float r)
        {
            var top = new PointF(cx, cy - r);
            var left = new PointF(cx - r * 0.82f, cy - r * 0.45f);
            var right = new PointF(cx + r * 0.82f, cy - r * 0.45f);
            var bottom = new PointF(cx, cy);
            var leftBottom = new PointF(left.X, left.Y + r);
            var rightBottom = new PointF(right.X, right.Y + r);
            g.DrawLine(p, top, left);
            g.DrawLine(p, top, right);
            g.DrawLine(accent, left, bottom);
            g.DrawLine(p, right, bottom);
            g.DrawLine(p, left, leftBottom);
            g.DrawLine(p, right, rightBottom);
            g.DrawLine(p, bottom, new PointF(bottom.X, bottom.Y + r));
            g.DrawLine(p, leftBottom, new PointF(bottom.X, bottom.Y + r));
            g.DrawLine(accent, rightBottom, new PointF(bottom.X, bottom.Y + r));
        }

        private void AsterMaxDrawViewFace(Graphics g, Pen p, Pen accent, string label)
        {
            g.DrawRectangle(p, 8, 8, 16, 16);
            g.DrawLine(accent, 8, 8, 24, 24);
            using (var f = new Font("Segoe UI Semibold", 7.5f, FontStyle.Bold))
            using (var b = new SolidBrush(Color.FromArgb(58, 64, 72)))
            using (var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                g.DrawString(label, f, b, new RectangleF(8, 8, 16, 16), sf);
        }

'@
if(-not $u.Contains($helperAnchor)) { throw 'C10.25 icon helper insertion anchor missing.' }
$u = $u.Replace($helperAnchor,$helpers+$helperAnchor)

Set-Content $ui $u -Encoding UTF8
Write-Host 'C10.25: Mechanical-inspired original engineering ribbon icons applied.' -ForegroundColor Green
