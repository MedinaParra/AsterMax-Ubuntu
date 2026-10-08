"""Geometry screening of original 1604. No design changes or FEA."""
import json,math
slab=200.;cover=50.;d=16.;leg=100.;width=900.
available=slab-2*cover
report={"source":"SPC-0090-CL-CFD-036002/036003 mark1604 and sectionB",
"status":"SOURCE_GEOMETRY_AMBIGUITY_NOT_FABRICATION_RELEASE",
"available_outer_depth_mm":available,"checks":[]}
report["checks"].append({"hypothesis":"100 is centerline depth",
"required_outer_depth_mm":leg+d,"fits":leg+d<=available,
"result":"FAIL_GEOMETRY under this interpretation only"})
depth=leg-d
ytop=-cover-d/2;ybottom=-slab+cover+d/2
assert abs((ytop-ybottom)-depth)<1e-9
report["checks"].append({"hypothesis":"100 is outside depth",
"centerline_depth_mm":depth,"centerline_width_mm":width-d,
"outer_cover_mm":cover,"fits_envelope":True,
"result":"CONDITIONAL_ENVELOPE_FIT; dimension convention not confirmed"})
report["checks"].append({"hypothesis":"upper and lower U at identical x station, same side-leg axes",
"leg_axis_overlap_without_bend_allowance_mm":depth,
"result":"INTERFERENCE under coincident placement; relative station and bend geometry unresolved"})
report["next_required_geometry"]=["dimension convention","bend mandrel/radius",
"upper/lower U relative longitudinal stations","bar crossing order",
"exact new-end hook geometry; do not adopt straight proposal as original"]
report["prohibitions"]=["no automatic cover reduction","no diameter reduction",
"no automatic upper/lower stagger treated as source detail",
"no final mass from duplicate/overlapping solids"]
print(json.dumps(report,indent=2))
