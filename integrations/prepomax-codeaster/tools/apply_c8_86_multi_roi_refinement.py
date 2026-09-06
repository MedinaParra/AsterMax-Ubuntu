#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/PrePoMax-CodeAster')
path = root / 'PrePoMax' / 'Controller.cs'
text = path.read_text(encoding='utf-8-sig')
anchor = '''            CreateMeshRefinementFile(part, meshRefinementFileName, null);'''
replacement = '''            CreateMeshRefinementFile(part, meshRefinementFileName, null);

            // C8.86 harness-only multi-ROI qualification seam. This writes the exact NetGen
            // mesh-size point contract at the consumer boundary. It does NOT claim that native
            // FeMeshRefinement / GUI geometry binding is qualified yet.
            string c886Points = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_REFINEMENT_POINTS");
            if (!String.IsNullOrWhiteSpace(c886Points))
            {
                string[] c886Specs = c886Points.Split(new char[] { ';' }, StringSplitOptions.RemoveEmptyEntries);
                if (c886Specs.Length == 0) throw new InvalidOperationException("C8.86 refinement point contract is empty.");
                using (System.IO.StreamWriter c886Writer = new System.IO.StreamWriter(meshRefinementFileName, false))
                {
                    c886Writer.WriteLine(c886Specs.Length.ToString(System.Globalization.CultureInfo.InvariantCulture));
                    foreach (string c886Spec in c886Specs)
                    {
                        string[] c886Vals = c886Spec.Split(',');
                        if (c886Vals.Length != 4) throw new InvalidOperationException("C8.86 point must be x,y,z,h.");
                        double[] c886Num = new double[4];
                        for (int c886I = 0; c886I < 4; c886I++)
                        {
                            if (!Double.TryParse(c886Vals[c886I], System.Globalization.NumberStyles.Float,
                                                 System.Globalization.CultureInfo.InvariantCulture, out c886Num[c886I]) ||
                                Double.IsNaN(c886Num[c886I]) || Double.IsInfinity(c886Num[c886I]))
                                throw new InvalidOperationException("C8.86 point contains a non-finite value.");
                        }
                        if (c886Num[3] <= 0) throw new InvalidOperationException("C8.86 local h must be > 0 mm.");
                        c886Writer.WriteLine(String.Format(System.Globalization.CultureInfo.InvariantCulture,
                            "{0:R} {1:R} {2:R} {3:R}", c886Num[0], c886Num[1], c886Num[2], c886Num[3]));
                    }
                    c886Writer.WriteLine("0"); // zero refined segments; point refinements only
                }

                // Only adaptive runs request/capture refinement evidence. A clean baseline must
                // neither require nor synthesize meshRefinement evidence; this keeps absence of
                // local refinement distinct from missing evidence.
                string c886Copy = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_REFINEMENT_COPY_PATH");
                if (!String.IsNullOrWhiteSpace(c886Copy))
                {
                    string c886Dir = Path.GetDirectoryName(c886Copy);
                    if (!String.IsNullOrWhiteSpace(c886Dir)) Directory.CreateDirectory(c886Dir);
                    File.Copy(meshRefinementFileName, c886Copy, true);
                }
            }'''
if anchor not in text:
    raise SystemExit('C8.86 CreateMeshRefinementFile anchor not found; refusing non-deterministic patch')
text = text.replace(anchor, replacement, 1)
path.write_text(text, encoding='utf-8')
print(f'C8.86 multi-ROI NetGen refinement seam applied: {path}')
