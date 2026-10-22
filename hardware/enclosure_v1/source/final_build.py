"""Authoritative consolidated prototype build, units mm. Run from any directory.
STL/STEP exports plus BREP, interference and mesh checks. No camera/motor hardware.
"""
from Plots.instruments_v1.source.enclosure import cq,cyl,ring,sector,PROJECT
import math,json,csv,hashlib,zipfile,shutil
import trimesh
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
ROOT=PROJECT/'final'
for sub in ('stl','step','reference','fit-test','reports','source'):
    (ROOT/sub).mkdir(parents=True,exist_ok=True)
EPS=.01
def log(t):print(t,flush=True)
def box(x0,y0,x1,y1,z,h):return cq.Solid.makeBox(x1-x0,y1-y0,h,cq.Vector(x0,y0,z))
def lap(a,z,h,r0=10,r1=90,half=5):
    a=math.radians(a);u=(math.cos(a),math.sin(a));v=(-math.sin(a),math.cos(a))
    pts=[(r*u[0]+t*v[0],r*u[1]+t*v[1]) for r,t in [(r0,-half),(r1,-half),(r1,half),(r0,half)]]
    return cq.Workplane('XY').polyline(pts).close().extrude(h).val().translate((0,0,z))
def split(s,start,holes):
    s=s.intersect(sector(0,105,start,start+90,-10,112))
    # Nominal 2+2 lap; 0.15 total vertical relief and 0.2 at ends/edges.
    s=s.cut(lap(start,-.01,2.085,9.8,90.2,5.2)).fuse(lap(start,2.075,1.925))
    s=s.cut(lap(start+90,1.925,2.085,9.8,90.2,5.2)).fuse(lap(start+90,0,1.925))
    for deg in (start,start+90):
        a=math.radians(deg)
        for r in holes:s=s.cut(cyl(1.8,5,z=-.5,x=r*math.cos(a),y=r*math.sin(a)))
    return s.clean()
def rotate(s,a):return s.rotate((0,0,0),(0,0,1),a)
def fuse_all(ss):
    s=ss[0]
    for t in ss[1:]:s=s.fuse(t)
    return s.clean()
def compound(ss):return cq.Compound.makeCompound(ss)

warnings=[
 'Prototype housing and previously discussed holders only; camera/stepper supports and drive transmission are not designed.',
 'Plain sliding ring is gravity seated, with no positive anti-lift latch. Friction, wear, lubrication compatibility and motor torque are not physically verified.',
 'Sliding tracks cross four printed seams; surface steps must be removed before powered rotation.',
 'FDM dimensions vary. Test the supplied sliding-ring coupons and M3 holes before printing all pieces.',
 'STL has no unit metadata; import as mm. Support generation and slicer toolpath have not been verified.',
 'All metal screws, nuts, washers, slip ring and electronics are purchased parts and not included in STL.',
 'Board underside components and connector clearances remain unmeasured; locator fits nominal 100x79 and 80x50 rectangles.',
 'Floor-fastener projections under the board locator must stay within 5 mm above floor; complete full 360 cable travel with a slip ring, not loose tethered wires.'
]
rep={'unit':'mm','errors':[],'warnings':warnings,'corrections':[
 'Rebuilt tier1 at wall4/floor4 and split into four identical quarters; older wall3 construction not used.',
 'Battery base D192.8 did not fit ID192 or printer180. Trimmed only perimeter to 170x170 and R95.65; retained guide/screw features.',
 'Battery base mounts via four outer R85 floor fasteners instead of obsolete three mounting bosses; inner R15 bolt reliefs added.',
 'Integrated plain bearing: tier2 top flange R92..100, groove R94.6..97.4 at z96..100; tier3 tongue R95..97, height5. Axial housing gap1, side clearances0.4.',
 'Floor lap nominal2+2 now includes 0.15 vertical and 0.2 edge/end clearance, to avoid exact interference fits.'
 ,'Helical screw default CAD volume differed by about 0.53 percent from adaptive integration. Adaptive BREP integration is used for STL volume checks; high-resolution mesh agreed within about 0.0034 percent.'
 ,'Eight locator corners had line-only contact between stop arms, producing 4-face STL edges. Added 2x2 corner fills to make continuous L corners.'
 ],'parts':{},'checks':{}}
parts={};counts={}
def keep(n,s,q):
    assert s.isValid() and len(s.Solids())==1,(n,'invalid solid',len(s.Solids()))
    parts[n]=s;counts[n]=q

log('1/7 Building tier 1, four identical quarters and concealed J slots')
t1=cyl(100,100).cut(cyl(96,100,z=4))
for a in (0,90,180,270):
    t1=t1.cut(sector(95.8,98.35,a-2.6,a+2.6,94.95,100.1))
    t1=t1.cut(sector(95.8,98.35,a-2.6,a+22.6,94.95,98.15))
    t1=t1.cut(sector(95.8,98.35,a+17.4,a+22.6,94.15,98.15))
    t1=t1.cut(cyl(2.5,5,z=-.5,x=50*math.cos(math.radians(a)),y=50*math.sin(math.radians(a))))
keep('1_1',split(t1,45,(15,85)),4)
q1=[rotate(parts['1_1'],a) for a in (0,90,180,270)]

log('2/7 Building tier 2 with sliding groove and lower bayonet')
collar=ring(92.65,95.65,-8,.1).fuse(ring(92.65,100,0,4))
for a in (0,90,180,270):collar=collar.fuse(sector(95.35,98,a-2.2,a+2.2,-5.5,-3))
t2=cyl(100,100).cut(cyl(96,100,z=4)).fuse(collar)
t2=t2.fuse(ring(92,100,92,100)).cut(ring(94.6,97.4,96,100.1))
t2=t2.cut(cyl(10,5,z=-.5))
for a in (0,90,180,270):
    a=math.radians(a)
    t2=t2.cut(cyl(2.5,5,z=-.5,x=50*math.cos(a),y=50*math.sin(a)))
    t2=t2.cut(cyl(4,5,z=-.5,x=88*math.cos(a),y=88*math.sin(a)))
for n,angles in [('2_1',(60,120)),('2_2',(90,))]:
    s=split(t2,45,(15,85))
    for a in angles:
        a=math.radians(a);dx,dy=math.cos(a),math.sin(a)
        s=s.cut(cyl(5,14,z=50,x=90*dx,y=90*dy,direction=(dx,dy,0)))
    keep(n,s.clean(),2)
q2=[parts['2_1'],rotate(parts['2_2'],90),rotate(parts['2_1'],180),rotate(parts['2_2'],270)]

log('3/7 Building tier 3, slot15 in XZ and sliding tongue')
t3=cq.Solid.makeSphere(100).cut(cq.Solid.makeSphere(96)).fuse(cyl(100,4))
t3=t3.cut(box(-105,-7.5,105,7.5,4,101)).fuse(ring(95,97,-5,.1)).clean()
keep('3_1',split(t3,45,(50,)),2)
keep('3_2',rotate(split(t3,135,(50,)),-90),2)
q3=[parts['3_1'],rotate(parts['3_2'],90),rotate(parts['3_1'],180),rotate(parts['3_2'],270)]

log('4/7 Adapting battery components and importing board locator')
bparts={}
for p in sorted((PROJECT/'geometry'/'battery-clamp').glob('*.step')):
    bparts[p.stem]=cq.importers.importStep(str(p)).val()
bbase=bparts['03_insert_slider_base'].intersect(cyl(95.65,26)).intersect(box(-85,-85,85,85,-1,27))
for a in (45,135,225,315):
    a=math.radians(a)
    bbase=bbase.cut(cyl(5,26,z=-.5,x=15*math.cos(a),y=15*math.sin(a)))
    bbase=bbase.cut(cyl(1.8,26,z=-.5,x=85*math.cos(a),y=85*math.sin(a)))
bparts['03_insert_slider_base']=bbase.clean()
for n,s in bparts.items():keep('battery_'+n,s,1)
locator=cq.importers.importStep(str(PROJECT/'geometry'/'tier2-variants'/'board-XY-locator.step')).val()
for cx,cy,w,d in [(0,-25,100,79),(0,55,80,50)]:
    for sx in (-1,1):
        for sy in (-1,1):
            x=cx+sx*(w/2+.3);y=cy+sy*(d/2+.3)
            xa,xb=(x,x+2) if sx>0 else (x-2,x)
            ya,yb=(y,y+2) if sy>0 else (y-2,y)
            locator=locator.fuse(box(xa,ya,xb,yb,10,3))
locator=locator.clean()
keep('board_XY_locator',locator,1)

log('5/7 Validating assembly, J motion, sliding rotation and fasteners')
for tier,qs in [('tier1',q1),('tier2',q2),('tier3',q3)]:
    vals=[]
    for i in range(4):
        for j in range(i+1,4):
            v=qs[i].intersect(qs[j]).Volume()
            assert v<.01,(tier,i,j,v)
            vals.append(v)
    rep['checks'][tier+'_quarter_overlaps']=vals
full1=compound(q1); full2=compound(q2);full3=compound(q3)
bay=[]
for z,a in [(z,0) for z in (110,108,106,104,102,100.8)]+[(100.8,a) for a in (0,5,10,15,20)]+[(z,20) for z in (100.8,100.4,100)]:
    v=full1.intersect(rotate(full2,a).translate((0,0,z))).Volume()
    assert v<.01,('bayonet',z,a,v)
    bay.append({'z':z,'angle':a,'interference':v})
rep['checks']['bayonet_path']=bay
locked2=rotate(full2,20).translate((0,0,100))
rot=[]
for a in (0,15,30,45,60,90,135,180,270,360):
    v=locked2.intersect(rotate(full3,a).translate((0,0,201))).Volume()
    assert v<.01,('yaw',a,v)
    rot.append({'angle':a,'interference':v})
rep['checks']['tier3_yaw_samples']=rot
assert locator.intersect(full2).Volume()<.01
bat=[s.translate((0,0,4)) for s in bparts.values()]
batchecks=[]
for i,a in enumerate(bat):
    v=a.intersect(full1).Volume(); assert v<.01,('battery housing',i,v)
    for j in range(i+1,len(bat)):
        v=a.intersect(bat[j]).Volume();assert v<.01,('battery pair',i,j,v)
        batchecks.append(v)
rep['checks']['battery_pair_overlaps']=batchecks
rep['checks']['board_locator_housing_overlap']=locator.intersect(full2).Volume()
for r,z,h in [(4,-9,35)]:
    for x,y in ((0,88),(88,0),(0,-88),(-88,0)):
        p=cyl(r,h,z=z,x=x,y=y)
        assert full2.intersect(p).Volume()+locator.intersect(p).Volume()<.001
rep['checks']['four_D8_power_paths']='clear of tier2 and locator'

log('6/7 Exporting STL and checking watertight meshes')
def export(n,s,q=1,folder='stl'):
    cq.exporters.export(s,str(ROOT/'step'/(n+'.step')))
    oriented=s
    if n in ('battery_01_adjustment_screw','battery_02_threaded_moving_slide','battery_05_shaft_retaining_clip'):
        oriented=s.rotate((0,0,0),(0,1,0),-90)
    bb=oriented.BoundingBox()
    oriented=oriented.translate((-(bb.xmin+bb.xmax)/2,-(bb.ymin+bb.ymax)/2,-bb.zmin))
    path=ROOT/folder/(n+'.stl')
    oriented.exportStl(str(path),tolerance=.035,angularTolerance=.10,relative=False)
    mesh=trimesh.load_mesh(str(path),process=True)
    repaired=False
    if not mesh.is_winding_consistent or mesh.volume<0:
        mesh.fix_normals();mesh.export(str(path));repaired=True
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0,(n,'bad mesh')
    components=len(mesh.split(only_watertight=False));assert components==1,(n,components)
    dims=mesh.extents.tolist();assert max(dims)<180,(n,dims)
    prop=GProp_GProps()
    integration_error=BRepGProp.VolumeProperties_s(s.wrapped,prop,1e-7,True,False)
    exact_volume=prop.Mass()
    rec={'quantity':q,'dimensions_mm':dims,'triangles':len(mesh.faces),'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),'components':components,'volume_mm3':float(mesh.volume),'adaptive_BREP_volume_mm3':exact_volume,'CAD_volume_integration_error_estimate':integration_error,'STL_volume_difference_ratio':abs(mesh.volume-exact_volume)/exact_volume,'normal_repair':repaired}
    assert rec['STL_volume_difference_ratio']<.005,(n,'mesh volume mismatch',rec)
    rep['parts'][n]=rec
    log('  '+n+' : '+str(tuple(round(d,2) for d in dims))+' x'+str(q))
for n,s in parts.items():export(n,s,counts[n])
# Short curved test pieces use the exact final radius/groove/tongue.
low=ring(92,100,92,100).cut(ring(94.6,97.4,96,100.1)).intersect(sector(0,101,80,100,90,105)).clean()
up=ring(95,97,-5,.1).fuse(ring(92,100,0,2)).intersect(sector(0,101,80,100,-6,4)).clean()
export('fit_lower_groove',low,1,'fit-test');export('fit_upper_tongue',up,1,'fit-test')

assembly=cq.Compound.makeCompound(q1+[rotate(s,20).translate((0,0,100)) for s in q2]+[s.translate((0,0,201)) for s in q3]+bat+[rotate(locator,20).translate((0,0,100))])
cq.exporters.export(assembly,str(ROOT/'reference'/'assembly.step'))
for n,s in [('tier1_assembly',full1),('tier2_assembly',full2),('tier3_assembly',full3)]:cq.exporters.export(s,str(ROOT/'reference'/(n+'.step')))
rep['counts']={'unique_main_STL_files':len(parts),'main_printed_pieces':sum(counts.values()),'optional_fit_test_pieces':2}
rep['hardware']={'tier1_floor_bolt_positions':8,'tier2_floor_bolt_positions':8,'tier3_floor_bolt_positions':4,'floor_fastener':'M3 with D3.6 clearance, washers and nuts; bolt lengths must suit actual stack','battery_base':'Uses tier1 outer four R85 fastening positions, no extra floor holes','printed_battery_thread':'custom D10 P2, not ISO M10'}
(ROOT/'reports'/'verification.json').write_text(json.dumps(rep,indent=2),encoding='utf-8')
with (ROOT/'reports'/'print-list.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f);w.writerow(['STL','quantity','X_mm','Y_mm','Z_mm','triangles'])
    for n in parts:
        rr=rep['parts'][n];w.writerow([n+'.stl',counts[n],*[round(x,3) for x in rr['dimensions_mm']],rr['triangles']])
shutil.copy2(__file__,ROOT/'source'/'final_build.py')
shutil.copy2(PROJECT/'source'/'enclosure.py',ROOT/'source'/'enclosure.py')
log('7/7 All geometric and mesh checks passed; generating guide/preview is next')
