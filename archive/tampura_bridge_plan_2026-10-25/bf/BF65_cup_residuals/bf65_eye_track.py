import json, sys
p, name = sys.argv[1], sys.argv[2]
r3 = lambda v: [round(float(x), 3) for x in v] if v is not None else None
last = None
prev = None
with open(p, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        last = r
        o = next((o for o in r.get("objects", []) if o["name"] == name), None)
        sh = [(s["id"], [r3(a) for a in s["aabb"]], s.get("status")) for s in r.get("shadows", []) if s.get("caster") == name]
        state = (o.get("is_occluder") if o else None, tuple(o.get("shadow_ids") or []) if o else None, str(sh), r.get("belief", {}).get("known_empty") and tuple(r["belief"]["known_empty"]))
        if state != prev:
            print(f"#{r['k']} {str(r.get('tag'))[:80]}")
            if o: print(f"   {name}: true {r3(o.get('true_pos'))} tilt {o.get('tilt_deg')} err {o.get('err_mm')} occ {o.get('is_occluder')} sh {o.get('shadow_ids')}")
            print(f"   shadows {sh}")
            print(f"   known_empty {r.get('belief', {}).get('known_empty')} unknown {r.get('belief', {}).get('unknown')}")
            prev = state
print("LAST", last["k"], str(last.get("tag"))[:100])