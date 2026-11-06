import json, sys
p, names = sys.argv[1], sys.argv[2].split(",")
maxrec = int(sys.argv[3]) if len(sys.argv) > 3 else 999
r3 = lambda v: [round(float(x), 3) for x in v] if v is not None else None
with open(p, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r["k"] > maxrec: break
        cam = r.get("camera") or {}
        print(f"#{r['k']} {str(r.get('tag'))[:70]} | cam {r3(cam.get('position'))} -> {r3(cam.get('target'))}")
        for o in r.get("objects", []):
            if o["name"] in names:
                ba = o.get("believed_aabb")
                print(f"   {o['name']}: true {r3(o.get('true_pos'))} tilt {o.get('tilt_deg')} true_aabb {[r3(a) for a in o.get('true_aabb') or []]} bel {[r3(a) for a in ba] if ba else None} err {o.get('err_mm')} px {o.get('visible_px')} occ {o.get('is_occluder')} sh {o.get('shadow_ids')} hid {o.get('hidden_by')}")
        for s in r.get("shadows", []):
            if s.get("caster") in names:
                print(f"   {s['id']}: {[r3(a) for a in s['aabb']]} {s.get('status')} blockers {s.get('blockers')}")