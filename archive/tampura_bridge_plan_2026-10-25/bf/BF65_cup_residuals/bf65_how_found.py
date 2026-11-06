import json, glob, os, sys, collections
root = sys.argv[1]
def classify(m):
    so = str(m.get("sense_outcomes") or "")
    if "found" in so:
        return "found by a sense"
    if (m.get("places") or 0) >= 1:
        return "after lifting a cup (no sense found it)"
    return "picked with nothing lifted"
for label, pattern, keep in [
        ("BF#63 generated scenes, arm O", "BF63_gen_scenes/eval/50630*/results.jsonl", lambda r: r.get("arm") == "O"),
        ("BF#59 shipped scenes, every arm", "BF59_slip/eval/*/results.jsonl", lambda r: True)]:
    c = collections.Counter(); outcomes = collections.Counter(); n = 0
    for p in sorted(glob.glob(os.path.join(root, pattern))):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            if not keep(r):
                continue
            rec = r.get("rec", r)
            m = rec.get("metrics") or {}
            ok = r.get("success", rec.get("bridge_status") == "success")
            if not ok:
                continue
            n += 1
            c[classify(m)] += 1
            outcomes[str(m.get("sense_outcomes"))] += 1
    print(label, "successes:", n)
    for k, v in c.most_common():
        print("   ", v, k)
    print("    sense_outcomes seen:", dict(outcomes.most_common(8)))