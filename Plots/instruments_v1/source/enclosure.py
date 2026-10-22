"""Final enclosure construction basis; no superseded electronics fixtures.
All dimensions are mm. Build returns two solids in their separate local frames.
The accepted 80x50 board layout is in design/board-layout.json.
Its detailed supports/clamps and tier 3 remain to be designed.
"""
from pathlib import Path
import sys, os, json, math
sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
LOCAL_LIB = PROJECT / 'runtime' / 'cad-libs'
if LOCAL_LIB.exists(): sys.path.insert(0, str(LOCAL_LIB))
os.environ.setdefault('XDG_CACHE_HOME', str(PROJECT/'runtime'/'cache'))
import cadquery as cq

def log(message):
    print(message, flush=True)

def cyl(r, height, z=0, x=0, y=0, direction=(0, 0, 1)):
    return cq.Solid.makeCylinder(r, height, cq.Vector(x, y, z), cq.Vector(*direction))

def ring(ri, ro, z0, z1):
    return cyl(ro, z1-z0, z=z0).cut(cyl(ri, z1-z0+0.2, z=z0-0.1))

def sector(ri, ro, a0, a1, z0, z1):
    outer = cq.Solid.makeCylinder(ro, z1-z0, cq.Vector(0, 0, z0),
                                 cq.Vector(0, 0, 1), a1-a0)
    outer = outer.rotate((0, 0, 0), (0, 0, 1), a0)
    return outer.cut(cyl(ri, z1-z0+0.2, z=z0-0.1))

def load_step(path):
    return cq.importers.importStep(str(path)).val()


def build(params=None):
    P = json.loads((PROJECT/'design'/'enclosure-parameters.json').read_text(encoding='utf-8'))
    if params: P.update(params)
    assert P['sensor_count'] * P['sensor_angle_step_deg'] == 360.0
    assert P['cable_guide_count'] * P['cable_guide_angle_step_deg'] == 360.0
    assert (P['outer_diameter'], P['body_height'], P['lower_bottom']) == (200, 100, 3), 'Imported baseline housing has fixed D200 H100 bottom3'
    R = P['outer_diameter']/2
    H = P['body_height']
    ri = P['collar_inner_radius']
    ro = P['collar_outer_radius']
    clearance = P['radial_clearance_each_side']
    assert abs(R-P['wall']-ro-clearance) < 1e-6, 'Collar OD and radial-clearance parameter disagree'
    lug_angles = [360.0*i/P['lug_count'] for i in range(P['lug_count'])]

    log('Importing original lower housing; preserving the D194 insertion opening')
    lower = load_step(PROJECT/'geometry'/'lower-housing-construction-base.step')
    for a in lug_angles:
        lower = lower.cut(sector(P['track_inner_radius'], P['track_outer_radius'],
                                 a-P['entry_half_angle_deg'], a+P['entry_half_angle_deg'],
                                 H-P['track_top'], H+0.1))
        lower = lower.cut(sector(P['track_inner_radius'], P['track_outer_radius'],
                                 a-P['entry_half_angle_deg'],
                                 a+P['lock_rotation_deg']+P['entry_half_angle_deg'],
                                 H-P['track_top'], H-P['track_bottom']))
    lower = lower.clean()

    log('Building upper housing with a downward collar, concealed lugs and central wire opening')
    upper = cyl(R, H).cut(cyl(R-P['wall'], H, z=P['upper_bottom']))
    lead = P['collar_lead_in']
    upper = upper.fuse(ring(ri, ro, -P['collar_height']+lead, 0.1))
    outer_lead = cq.Solid.makeCone(ro-lead, ro, lead, cq.Vector(0, 0, -P['collar_height']))
    inner_lead = cq.Solid.makeCone(ri+lead, ri, lead, cq.Vector(0, 0, -P['collar_height']))
    upper = upper.fuse(outer_lead.cut(inner_lead))
    for a in lug_angles:
        upper = upper.fuse(sector(P['lug_inner_radius'], P['lug_outer_radius'],
                                  a-P['lug_half_angle_deg'], a+P['lug_half_angle_deg'],
                                  -P['lug_top'], -P['lug_bottom']))
    wire_r = P['wire_bore_diameter']/2
    ch = P['wire_bore_edge_chamfer']
    wire = cyl(wire_r, P['upper_bottom']+0.2, z=-0.1)
    wire = wire.fuse(cq.Solid.makeCone(wire_r+ch, wire_r, ch, cq.Vector(0, 0, 0)))
    wire = wire.fuse(cq.Solid.makeCone(wire_r, wire_r+ch, ch,
                                     cq.Vector(0, 0, P['upper_bottom']-ch)))
    upper = upper.cut(wire)
    log('Adding six D5 through-floor cable ports on a 50 mm radius')
    guide_r = P['cable_guide_diameter']/2
    guide_ch = P['cable_guide_edge_chamfer']
    for i in range(P['cable_guide_count']):
        a = math.radians(P['cable_guide_start_angle_deg']+i*P['cable_guide_angle_step_deg'])
        x, y = P['cable_guide_pitch_radius']*math.cos(a), P['cable_guide_pitch_radius']*math.sin(a)
        guide = cyl(guide_r, P['upper_bottom']+0.2, z=-0.1, x=x, y=y)
        guide = guide.fuse(cq.Solid.makeCone(guide_r+guide_ch, guide_r, guide_ch, cq.Vector(x,y,0)))
        guide = guide.fuse(cq.Solid.makeCone(guide_r, guide_r+guide_ch, guide_ch,
                                           cq.Vector(x,y,P['upper_bottom']-guide_ch)))
        upper = upper.cut(guide)
    for i in range(P['sensor_count']):
        a = math.radians(i*P['sensor_angle_step_deg'])
        dx, dy = math.cos(a), math.sin(a)
        cutter = cyl(P['sensor_bore_diameter']/2, P['wall']+8,
                     z=P['sensor_center_height'], x=(R-P['wall']-4)*dx,
                     y=(R-P['wall']-4)*dy, direction=(dx, dy, 0))
        upper = upper.cut(cutter)
    upper = upper.clean()
    assert lower.isValid() and len(lower.Solids()) == 1
    assert upper.isValid() and len(upper.Solids()) == 1
    return {'lower_housing': lower, 'upper_housing': upper, 'parameters': P}
