from pathlib import Path

L=100.0
H=10.0
W=10.0
NX,NY,NZ=20,2,2
out=Path(__file__).with_name('cantilever.mail')

nodes=[]
node_id={}
idx=1
for i in range(NX+1):
    x=L*i/NX
    for j in range(NY+1):
        y=H*j/NY
        for k in range(NZ+1):
            z=W*k/NZ
            node_id[(i,j,k)]=idx
            nodes.append((idx,x,y,z))
            idx+=1

elems=[]
eid=1
for i in range(NX):
    for j in range(NY):
        for k in range(NZ):
            n000=node_id[(i,j,k)]
            n100=node_id[(i+1,j,k)]
            n110=node_id[(i+1,j+1,k)]
            n010=node_id[(i,j+1,k)]
            n001=node_id[(i,j,k+1)]
            n101=node_id[(i+1,j,k+1)]
            n111=node_id[(i+1,j+1,k+1)]
            n011=node_id[(i,j+1,k+1)]
            elems.append((eid,[n000,n100,n110,n010,n001,n101,n111,n011]))
            eid+=1

fixed=[node_id[(0,j,k)] for j in range(NY+1) for k in range(NZ+1)]
load=[node_id[(NX,j,k)] for j in range(NY+1) for k in range(NZ+1)]

with out.open('w', encoding='utf-8', newline='\n') as f:
    f.write('TITRE\nASTERMAX C9.81 B02 CANTILEVER - 100 x 10 x 10 mm - 80 HEXA8\nFINSF\n')
    f.write('COOR_3D\n')
    for nid,x,y,z in nodes:
        f.write(f'N{nid} {x:.6f} {y:.6f} {z:.6f}\n')
    f.write('FINSF\nHEXA8\n')
    for eid,conn in elems:
        f.write('E{} {}\n'.format(eid,' '.join(f'N{n}' for n in conn)))
    f.write('FINSF\nGROUP_NO\nFIXED {}\nFINSF\n'.format(' '.join(f'N{n}' for n in fixed)))
    f.write('GROUP_NO\nLOAD {}\nFINSF\nFIN\n'.format(' '.join(f'N{n}' for n in load)))

print(out)
print(f'nodes={len(nodes)} elements={len(elems)} fixed_nodes={len(fixed)} load_nodes={len(load)}')
