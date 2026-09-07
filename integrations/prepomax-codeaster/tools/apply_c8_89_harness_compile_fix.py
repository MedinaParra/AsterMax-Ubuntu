#!/usr/bin/env python3
from pathlib import Path
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    path = Path(args.repo).resolve() / "PrePoMax" / "AsterMaxAI" / "AsterMaxNativeRoiConsumerHarness.cs"
    text = path.read_text(encoding="utf-8-sig")

    # C8.89b: FeNode is a value type in the pinned upstream.
    old_guard = "if(!geometry.Nodes.TryGetValue(id,out node) || node==null) continue;"
    new_guard = "if(!geometry.Nodes.TryGetValue(id,out node)) continue;"
    if text.count(old_guard) == 1:
        text = text.replace(old_guard, new_guard, 1)
    elif new_guard not in text:
        raise RuntimeError("C8.89c could not establish FeNode value-type guard")

    # C8.89c: bind ROI to the actual tessellated surface, not merely its vertices.
    # Vertex-only distance falsely rejected ROI_03 on a large planar face even though
    # the ROI projects onto that face. Triangulate each visualization cell as a fan
    # and use the minimum Euclidean point-to-triangle distance.
    old_block = '''                HashSet<int> nodeIds=new HashSet<int>();
                foreach(int localCell in localCells)
                {
                    if(localCell<0 || localCell>=vis.Cells.Length || vis.Cells[localCell]==null) continue;
                    foreach(int id in vis.Cells[localCell]) nodeIds.Add(id);
                }
                if(nodeIds.Count==0) continue;
                double cx=0,cy=0,cz=0; int n=0; double nearest=Double.PositiveInfinity;
                foreach(int id in nodeIds)
                {
                    FeNode node;
                    if(!geometry.Nodes.TryGetValue(id,out node)) continue;
                    cx+=node.X; cy+=node.Y; cz+=node.Z; n++;
                    double dx=node.X-target.X,dy=node.Y-target.Y,dz=node.Z-target.Z;
                    double d=Math.Sqrt(dx*dx+dy*dy+dz*dz); if(d<nearest) nearest=d;
                }
'''
    new_block = '''                HashSet<int> nodeIds=new HashSet<int>();
                double nearest=Double.PositiveInfinity;
                foreach(int localCell in localCells)
                {
                    if(localCell<0 || localCell>=vis.Cells.Length || vis.Cells[localCell]==null) continue;
                    int[] cell=vis.Cells[localCell];
                    foreach(int id in cell) nodeIds.Add(id);
                    if(cell.Length>=3)
                    {
                        FeNode a,b,c;
                        if(!geometry.Nodes.TryGetValue(cell[0],out a) || !geometry.Nodes.TryGetValue(cell[1],out b)) continue;
                        for(int k=2;k<cell.Length;k++)
                        {
                            if(!geometry.Nodes.TryGetValue(cell[k],out c)) continue;
                            double d=PointTriangleDistance(target.X,target.Y,target.Z,a,b,c);
                            if(d<nearest) nearest=d;
                            b=c;
                        }
                    }
                }
                if(nodeIds.Count==0) continue;
                double cx=0,cy=0,cz=0; int n=0;
                foreach(int id in nodeIds)
                {
                    FeNode node;
                    if(!geometry.Nodes.TryGetValue(id,out node)) continue;
                    cx+=node.X; cy+=node.Y; cz+=node.Z; n++;
                }
'''
    if text.count(old_block) != 1:
        if "PointTriangleDistance(target.X,target.Y,target.Z,a,b,c)" in text:
            raise RuntimeError("C8.89c surface-distance fix already present; refusing duplicate patch")
        raise RuntimeError("C8.89c expected exactly one vertex-distance block, found %d" % text.count(old_block))
    text = text.replace(old_block, new_block, 1)

    helper_anchor = "        private static bool Finite(double v) { return !Double.IsNaN(v)&&!Double.IsInfinity(v); }"
    helper = '''        private static double PointTriangleDistance(double px,double py,double pz,FeNode a,FeNode b,FeNode c)
        {
            double abx=b.X-a.X, aby=b.Y-a.Y, abz=b.Z-a.Z;
            double acx=c.X-a.X, acy=c.Y-a.Y, acz=c.Z-a.Z;
            double apx=px-a.X, apy=py-a.Y, apz=pz-a.Z;
            double d1=abx*apx+aby*apy+abz*apz;
            double d2=acx*apx+acy*apy+acz*apz;
            if(d1<=0 && d2<=0) return Math.Sqrt(apx*apx+apy*apy+apz*apz);

            double bpx=px-b.X, bpy=py-b.Y, bpz=pz-b.Z;
            double d3=abx*bpx+aby*bpy+abz*bpz;
            double d4=acx*bpx+acy*bpy+acz*bpz;
            if(d3>=0 && d4<=d3) return Math.Sqrt(bpx*bpx+bpy*bpy+bpz*bpz);

            double vc=d1*d4-d3*d2;
            if(vc<=0 && d1>=0 && d3<=0)
            {
                double v=d1/(d1-d3);
                double qx=a.X+v*abx, qy=a.Y+v*aby, qz=a.Z+v*abz;
                double dx=px-qx,dy=py-qy,dz=pz-qz; return Math.Sqrt(dx*dx+dy*dy+dz*dz);
            }

            double cpx=px-c.X, cpy=py-c.Y, cpz=pz-c.Z;
            double d5=abx*cpx+aby*cpy+abz*cpz;
            double d6=acx*cpx+acy*cpy+acz*cpz;
            if(d6>=0 && d5<=d6) return Math.Sqrt(cpx*cpx+cpy*cpy+cpz*cpz);

            double vb=d5*d2-d1*d6;
            if(vb<=0 && d2>=0 && d6<=0)
            {
                double w=d2/(d2-d6);
                double qx=a.X+w*acx, qy=a.Y+w*acy, qz=a.Z+w*acz;
                double dx=px-qx,dy=py-qy,dz=pz-qz; return Math.Sqrt(dx*dx+dy*dy+dz*dz);
            }

            double va=d3*d6-d5*d4;
            if(va<=0 && (d4-d3)>=0 && (d5-d6)>=0)
            {
                double w=(d4-d3)/((d4-d3)+(d5-d6));
                double qx=b.X+w*(c.X-b.X), qy=b.Y+w*(c.Y-b.Y), qz=b.Z+w*(c.Z-b.Z);
                double dx=px-qx,dy=py-qy,dz=pz-qz; return Math.Sqrt(dx*dx+dy*dy+dz*dz);
            }

            double denom=1.0/(va+vb+vc), v2=vb*denom, w2=vc*denom;
            double fx=a.X+abx*v2+acx*w2, fy=a.Y+aby*v2+acy*w2, fz=a.Z+abz*v2+acz*w2;
            double fdx=px-fx,fdy=py-fy,fdz=pz-fz; return Math.Sqrt(fdx*fdx+fdy*fdy+fdz*fdz);
        }

'''
    if text.count(helper_anchor) != 1:
        raise RuntimeError("C8.89c Finite helper anchor not unique")
    text = text.replace(helper_anchor, helper + helper_anchor, 1)

    path.write_text(text, encoding="utf-8")
    print("C8.89c point-to-triangle native CAD surface distance + FeNode contract applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
