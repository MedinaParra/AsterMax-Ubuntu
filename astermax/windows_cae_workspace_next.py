"""AsterMax next-level CAE workspace for Windows.

Dominant 3D workspace + ribbon + model tree + engineering copilot. Preview TRI3
selection is explicit proposal-authoring context only; it is not solver evidence
or persistent CAD topology identity.
"""
from __future__ import annotations

import math
from pathlib import Path
import threading

from .viewport_selection import SurfacePick, parse_force_command, pick_triangle, project_nodes
from .windows_app import WindowsAppError, validate_step_mm_file
from .windows_cae_workspace import PreviewMesh, build_step_preview


def launch_desktop() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    BG="#0B0F14"; PANEL="#111820"; RIBBON="#151D26"; BORDER="#26313D"; TEXT="#EDF3F8"; MUTED="#8291A2"
    ACCENT="#21A5FF"; FACE="#263B4E"; EDGE="#426983"; SELECT="#FFB64D"; GREEN="#4ED69C"
    root=tk.Tk(); root.title("AsterMax — Engineering Intelligence Workspace"); root.geometry("1660x980"); root.minsize(1250,760); root.configure(bg=BG)
    try: root.state("zoomed")
    except tk.TclError: pass
    style=ttk.Style(root)
    try: style.theme_use("clam")
    except tk.TclError: pass
    style.configure("TFrame",background=BG); style.configure("Ribbon.TFrame",background=RIBBON); style.configure("Panel.TFrame",background=PANEL)
    style.configure("Ribbon.TButton",background=RIBBON,foreground=TEXT,padding=(14,8),borderwidth=0)
    style.map("Ribbon.TButton",background=[("active","#22303D")])
    style.configure("Accent.TButton",background=ACCENT,foreground="white",padding=(15,9),borderwidth=0,font=("Segoe UI Semibold",10))
    style.configure("Treeview",background=PANEL,fieldbackground=PANEL,foreground=TEXT,borderwidth=0,rowheight=27)
    style.map("Treeview",background=[("selected","#1C5C85")]); style.configure("TLabel",background=BG,foreground=TEXT)

    state={"step":None,"mesh":None,"pick":None,"analysis":None,"fixed":None,"force":None,"approved":False,"press":None}
    status=tk.StringVar(value="Ready — import STEP geometry")

    # title + ribbon
    title=tk.Frame(root,bg="#080C10",height=34); title.pack(fill="x"); title.pack_propagate(False)
    tk.Label(title,text="ASTERMAX",fg="white",bg="#080C10",font=("Segoe UI Black",13)).pack(side="left",padx=(14,8))
    tk.Label(title,text="ENGINEERING INTELLIGENCE",fg=MUTED,bg="#080C10",font=("Segoe UI",9)).pack(side="left")
    tk.Label(title,text="mm · N · MPa",fg=MUTED,bg="#080C10",font=("Segoe UI",9)).pack(side="right",padx=14)
    tabs=tk.Frame(root,bg=RIBBON,height=30); tabs.pack(fill="x"); tabs.pack_propagate(False)
    for name in ("File","Geometry","Model","Connections","Mesh","Analysis","Results","Automation"):
        tk.Label(tabs,text=name,fg=TEXT,bg=RIBBON,font=("Segoe UI",9),padx=13,pady=6).pack(side="left")
    commands=ttk.Frame(root,style="Ribbon.TFrame",padding=(8,7)); commands.pack(fill="x")

    body=tk.PanedWindow(root,orient="horizontal",sashwidth=5,bg=BORDER,bd=0); body.pack(fill="both",expand=True)
    left=tk.Frame(body,bg=PANEL,width=270); center=tk.Frame(body,bg=BG); right=tk.Frame(body,bg=PANEL,width=340)
    body.add(left,minsize=210); body.add(center,minsize=650); body.add(right,minsize=270)

    # model tree
    tk.Label(left,text="MODEL TREE",fg=MUTED,bg=PANEL,font=("Segoe UI Semibold",9),anchor="w").pack(fill="x",padx=12,pady=(12,5))
    tree=ttk.Treeview(left,show="tree",selectmode="browse"); tree.pack(fill="both",expand=True,padx=4,pady=(0,6))
    model=tree.insert("","end",text="▾ Model",open=True); geom=tree.insert(model,"end",text="  Geometry  [empty]")
    tree.insert(model,"end",text="  Materials"); tree.insert(model,"end",text="  Connections"); tree.insert(model,"end",text="  Mesh")
    selroot=tree.insert(model,"end",text="▾ Selections",open=True)

    # viewport
    canvas=tk.Canvas(center,bg=BG,highlightthickness=0); canvas.pack(fill="both",expand=True)
    statusbar=tk.Frame(center,bg="#080C10",height=30); statusbar.pack(fill="x"); statusbar.pack_propagate(False)
    tk.Label(statusbar,textvariable=status,fg=MUTED,bg="#080C10",font=("Segoe UI",9)).pack(side="left",padx=10)
    tk.Label(statusbar,text="preview selection = proposal anchor · not solver evidence",fg=MUTED,bg="#080C10",font=("Segoe UI",9)).pack(side="right",padx=10)

    yaw=-0.65; pitch=0.45; zoom=1.0
    camera={"yaw":yaw,"pitch":pitch,"zoom":zoom}

    def draw():
        canvas.delete("all"); w=max(canvas.winfo_width(),2); h=max(canvas.winfo_height(),2); mesh=state["mesh"]
        if not mesh:
            canvas.create_text(w/2,h/2-18,text="3D ENGINEERING WORKSPACE",fill=TEXT,font=("Segoe UI Semibold",22))
            canvas.create_text(w/2,h/2+18,text="Import STEP / STP to begin",fill=MUTED,font=("Segoe UI",10)); return
        screen=project_nodes(mesh.nodes,width=w,height=h,yaw=camera["yaw"],pitch=camera["pitch"],zoom=camera["zoom"])
        tris=[]
        for idx,tri in enumerate(mesh.triangles):
            a,b,c=(screen[i] for i in tri); tris.append(((a[2]+b[2]+c[2])/3,idx,tri))
        tris.sort(key=lambda x:x[0]); stride=max(1,len(tris)//18000); selected=state["pick"].triangle_index if state["pick"] else -1
        for _,idx,tri in tris[::stride]:
            xy=[]
            for i in tri: xy.extend((screen[i][0],screen[i][1]))
            canvas.create_polygon(*xy,fill=(SELECT if idx==selected else FACE),outline=("#FFE0A3" if idx==selected else EDGE),width=(2 if idx==selected else 1))
        if selected>=0 and stride>1 and selected not in [item[1] for item in tris[::stride]]:
            tri=mesh.triangles[selected]; xy=[]
            for i in tri: xy.extend((screen[i][0],screen[i][1]))
            canvas.create_polygon(*xy,fill=SELECT,outline="#FFE0A3",width=2)
        canvas.create_text(14,14,anchor="nw",text=f"CAD PREVIEW • {len(mesh.nodes):,} nodes • {len(mesh.triangles):,} TRI3",fill="#9AA8B7",font=("Segoe UI",9))
        canvas.create_text(14,h-14,anchor="sw",text="Click: select surface triangle   •   Drag: orbit   •   Wheel: zoom",fill="#708091",font=("Segoe UI",9))

    def on_press(e): state["press"]=(e.x,e.y); state["drag_last"]=(e.x,e.y)
    def on_drag(e):
        last=state.get("drag_last");
        if not last:return
        dx,dy=e.x-last[0],e.y-last[1]; state["drag_last"]=(e.x,e.y); camera["yaw"]+=dx*.008; camera["pitch"]+=dy*.008; draw()
    def on_release(e):
        press=state.get("press"); state["drag_last"]=None
        if not press or math.hypot(e.x-press[0],e.y-press[1])>5:return
        mesh=state["mesh"]
        if not mesh:return
        try: picked=pick_triangle(mesh.nodes,mesh.triangles,x=e.x,y=e.y,width=max(canvas.winfo_width(),2),height=max(canvas.winfo_height(),2),yaw=camera["yaw"],pitch=camera["pitch"],zoom=camera["zoom"])
        except ValueError as exc: messagebox.showerror("AsterMax selection",str(exc)); return
        state["pick"]=picked
        if picked:
            status.set(f"Selected TRI3 #{picked.triangle_index} · centroid {tuple(round(v,3) for v in picked.centroid_mm)} mm")
            chat_line("AsterMax AI",f"Selected preview surface TRI3 #{picked.triangle_index}. You can say 'esta cara fija' or 'aplica 25 kN aqui en -Z'.")
        else: status.set("No surface under cursor")
        draw()
    def on_wheel(e): camera["zoom"]*=1.12 if e.delta>0 else 1/1.12; camera["zoom"]=max(.15,min(8,camera["zoom"])); draw()
    canvas.bind("<Configure>",lambda e:draw()); canvas.bind("<ButtonPress-1>",on_press); canvas.bind("<B1-Motion>",on_drag); canvas.bind("<ButtonRelease-1>",on_release); canvas.bind("<MouseWheel>",on_wheel)

    # AI panel
    tk.Label(right,text="ASTERMAX AI",fg=TEXT,bg=PANEL,font=("Segoe UI Semibold",11),anchor="w").pack(fill="x",padx=12,pady=(12,2))
    tk.Label(right,text="Engineering copilot · proposals remain explicit",fg=MUTED,bg=PANEL,font=("Segoe UI",9),anchor="w").pack(fill="x",padx=12,pady=(0,8))
    chat=tk.Text(right,bg="#0D1319",fg=TEXT,insertbackground=TEXT,relief="flat",wrap="word",font=("Segoe UI",9),state="disabled"); chat.pack(fill="both",expand=True,padx=10,pady=(0,8))
    prompt=tk.Text(right,height=4,bg="#090E13",fg=TEXT,insertbackground=TEXT,relief="flat",wrap="word",font=("Segoe UI",9)); prompt.pack(fill="x",padx=10)
    sendrow=tk.Frame(right,bg=PANEL); sendrow.pack(fill="x",padx=10,pady=8)
    def chat_line(who,text): chat.configure(state="normal"); chat.insert("end",f"{who}\n{text}\n\n"); chat.see("end"); chat.configure(state="disabled")
    chat_line("AsterMax AI","Load a STEP model, click a visible surface, then ask me to author a static-analysis proposal. I will not approve or solve it silently.")

    def ensure_analysis():
        if state["analysis"]: return state["analysis"]
        a=tree.insert(model,"end",text="▾ Static Structural",open=True); tree.insert(a,"end",text="  Analysis Settings"); state["analysis"]=a
        tree.insert(a,"end",text="▾ Solution",open=True); status.set("Static Structural created — waiting for BC/load proposals"); return a
    def selected_required():
        if not state["pick"]: raise WindowsAppError("Select a surface in the 3D viewport first")
        return state["pick"]
    def propose_fixed():
        p=selected_required(); a=ensure_analysis()
        if state["fixed"]: tree.delete(state["fixed"])
        node=tree.insert(a,"end",text=f"  Fixed Support [PROPOSED] · TRI3 {p.triangle_index}"); state["fixed"]=node; state["approved"]=False
        tree.insert(selroot,"end",text=f"  Surface Pick {p.triangle_index} · centroid {tuple(round(v,2) for v in p.centroid_mm)}")
        chat_line("AsterMax AI",f"Proposed Fixed Support on selected preview anchor TRI3 {p.triangle_index}. This is not approved and is not yet a persistent CAD face selection.")
    def propose_force(command):
        p=selected_required(); a=ensure_analysis()
        if state["force"]: tree.delete(state["force"])
        v=command.vector_n; node=tree.insert(a,"end",text=f"  Force [PROPOSED] · ({v[0]:g}, {v[1]:g}, {v[2]:g}) N · TRI3 {p.triangle_index}"); state["force"]=node; state["approved"]=False
        chat_line("AsterMax AI",f"Proposed force vector {v} N on selected preview anchor TRI3 {p.triangle_index}. Engineer approval is still required.")
    def approve_proposals():
        if not state["fixed"] or not state["force"]:
            messagebox.showwarning("AsterMax approval","A Fixed Support and Force proposal are both required before approval."); return
        tree.item(state["fixed"],text=tree.item(state["fixed"],"text").replace("[PROPOSED]","[APPROVED]")); tree.item(state["force"],text=tree.item(state["force"],"text").replace("[PROPOSED]","[APPROVED]")); state["approved"]=True
        status.set("Engineering intent approved — solver execution still uses verified preparation pipeline"); chat_line("AsterMax AI","Engineer approval recorded for the visible proposal tree. Solver execution remains separately gated by persistent model preparation.")
    def submit_ai():
        text=prompt.get("1.0","end").strip();
        if not text:return
        prompt.delete("1.0","end"); chat_line("You",text); low=text.lower()
        try:
            if ("cara" in low or "superficie" in low) and ("fij" in low or "fixed" in low): propose_fixed(); return
            force=parse_force_command(text)
            if force: propose_force(force); return
            if "estatic" in low or "static" in low or "analisis" in low or "análisis" in low: ensure_analysis(); chat_line("AsterMax AI","Static Structural analysis created. Select geometry and define BC/load proposals next."); return
            if "apro" in low: approve_proposals(); return
            chat_line("AsterMax AI","I recorded that instruction in the visible case context, but this PMV only executes deterministic authoring commands. No hidden engineering action was taken.")
        except WindowsAppError as exc: chat_line("AsterMax AI",f"BLOCKED: {exc}")
    ttk.Button(sendrow,text="SEND",style="Accent.TButton",command=submit_ai).pack(side="right")
    ttk.Button(sendrow,text="APPROVE",style="Ribbon.TButton",command=approve_proposals).pack(side="right",padx=6)

    # file loading / ribbon commands
    def preview_done(source,mesh): state["mesh"]=mesh; state["pick"]=None; tree.item(geom,text=f"  Geometry  [{source.name}]"); status.set(f"STEP preview ready — {len(mesh.nodes):,} nodes / {len(mesh.triangles):,} TRI3"); chat_line("AsterMax AI",f"STEP mm gate passed and 3D preview loaded: {source.name}. Click a surface to author model intent."); draw()
    def preview_failed(exc): status.set("STEP accepted but preview failed"); chat_line("AsterMax AI",f"Preview failed: {exc}"); messagebox.showerror("AsterMax preview",str(exc))
    def choose_step():
        path=filedialog.askopenfilename(title="Import STEP",filetypes=[("STEP","*.step *.stp"),("All files","*.*")]);
        if not path:return
        source=Path(path)
        try:validate_step_mm_file(source)
        except WindowsAppError as exc:messagebox.showerror("AsterMax STEP gate",str(exc));status.set("STEP blocked by mm trust gate");return
        state["step"]=source; tree.item(geom,text=f"  Geometry [{source.name}] — preview loading"); status.set("STEP mm gate passed — generating CAD preview…")
        def worker():
            try:m=build_step_preview(source)
            except Exception as exc:root.after(0,lambda e=exc:preview_failed(e));return
            root.after(0,lambda:preview_done(source,m))
        threading.Thread(target=worker,daemon=True).start()
    def fit(): camera.update(yaw=-.65,pitch=.45,zoom=1.0); draw()
    ttk.Button(commands,text="IMPORT STEP",style="Accent.TButton",command=choose_step).pack(side="left",padx=(0,6))
    ttk.Button(commands,text="NEW STATIC",style="Ribbon.TButton",command=ensure_analysis).pack(side="left")
    ttk.Button(commands,text="FIXED SUPPORT",style="Ribbon.TButton",command=lambda:safe(propose_fixed)).pack(side="left")
    ttk.Button(commands,text="APPROVE",style="Ribbon.TButton",command=approve_proposals).pack(side="left")
    ttk.Button(commands,text="FIT",style="Ribbon.TButton",command=fit).pack(side="left")
    ttk.Button(commands,text="MESH",style="Ribbon.TButton",command=lambda:chat_line("AsterMax AI","FEA mesh remains separate from CAD preview tessellation and requires persistent approved model preparation.")).pack(side="left")
    ttk.Button(commands,text="SOLVE",style="Ribbon.TButton",command=lambda:chat_line("AsterMax AI","Solve is intentionally not triggered from preview-only selections. Convert proposals to persistent model selections first.")).pack(side="left")
    def safe(fn):
        try:fn()
        except WindowsAppError as exc:messagebox.showwarning("AsterMax",str(exc))

    root.mainloop(); return 0


def main(argv=None) -> int:
    return launch_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
