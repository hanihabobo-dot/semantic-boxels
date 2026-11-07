#!/usr/bin/env python3
"""Path 6, phase 1b: merge the freshly generated find_dice scenes (the folder
tools/cluster/p6_gen_scenes.sbatch made: scenes/find_dice_gen_s<seed>.json and its
manifest.json) into the repository's scene directory and manifest
(tampura_bridge/gen_scenes/find_dice/), where G19 pins every scene by sha256.

  python tools/p6_merge_scenes.py <generated scenes dir> [--scenes-dir DIR] [--dry-run]

Nothing is filtered or replaced.  A seed that already has a scene in the
manifest is never touched (BF#63's seeds 100 to 139 stay as committed): a new
file for such a seed, or a name or sha256 that does not match the generated
manifest, stops the merge.  A seed the generator gave no scene stays listed in
the manifest's details with its error and has no entry under scenes.  The
generated manifest's own header (generator, made) goes under 'extensions'.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(os.path.dirname(HERE), 'tampura_bridge', 'gen_scenes', 'find_dice')


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def merge(gen_dir, scenes_dir, dry_run=False):
    """Merge; returns the new manifest.  Raises SystemExit on anything odd."""
    with open(os.path.join(gen_dir, 'manifest.json'), 'r', encoding='utf-8') as f:
        new = json.load(f)
    with open(os.path.join(scenes_dir, 'manifest.json'), 'r', encoding='utf-8') as f:
        old = json.load(f)
    clash = sorted(set(new['details']) & set(old['details']), key=int)
    if clash:
        raise SystemExit(f"seeds already in the manifest, never replaced: {clash[:10]}")
    for seed, name in new['scenes'].items():
        if name != f'find_dice_gen_s{seed}.json':
            raise SystemExit(f"seed {seed}: scene file named {name}")
        p = os.path.join(gen_dir, name)
        if not os.path.isfile(p):
            raise SystemExit(f"seed {seed}: {name} is not in {gen_dir}")
        if sha256(p) != new['details'][seed].get('sha256'):
            raise SystemExit(f"seed {seed}: {name} does not match its generated manifest's sha256")
        if os.path.exists(os.path.join(scenes_dir, name)):
            raise SystemExit(f"{name} exists in {scenes_dir} but not in its manifest")
    extra = sorted(n for n in os.listdir(gen_dir)
                   if n.endswith('.json') and n != 'manifest.json' and n not in new['scenes'].values())
    if extra:
        raise SystemExit(f"scene files the generated manifest does not list: {extra[:5]}")
    merged = dict(old)
    merged['scenes'] = {**old['scenes'], **new['scenes']}
    merged['details'] = {**old['details'], **new['details']}
    seeds = sorted(int(s) for s in new['details'])
    merged.setdefault('extensions', []).append(
        {'seeds': f"{seeds[0]}-{seeds[-1]}" if seeds else '', 'n_seeds': len(seeds),
         'n_scenes': len(new['scenes']), 'made': new.get('made'), 'generator': new.get('generator'),
         'what': new.get('what')})
    if not dry_run:
        for name in new['scenes'].values():
            shutil.copyfile(os.path.join(gen_dir, name), os.path.join(scenes_dir, name))
        with open(os.path.join(scenes_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=1)
    return merged


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('gen_dir', help="the generated folder (scene files and manifest.json)")
    ap.add_argument('--scenes-dir', default=DEFAULT_DIR)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    merged = merge(os.path.abspath(a.gen_dir), os.path.abspath(a.scenes_dir), a.dry_run)
    ext = merged['extensions'][-1]
    missing = sorted((s for s, d in merged['details'].items() if not d.get('scene')), key=int)
    print(f"{'would merge' if a.dry_run else 'merged'} seeds {ext['seeds']}: {ext['n_scenes']} scenes of "
          f"{ext['n_seeds']} seeds; the manifest now pins {len(merged['scenes'])} scenes"
          + (f"; NO SCENE for seeds {missing}" if missing else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
