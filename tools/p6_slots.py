"""Path 6 (cluster eval of our code now, our thesis code and TAMPURA): the seed
slots of phase 1a, the tabletop benchmark.  Shared by tools/cluster/p6_run.py
(which runs a slot), tools/p6_report.py (which reads the results) and the tests.

PLAN.md of the track (archive/tampura_bridge_plan_2026-10-25/tracks/eval/)
section 5 and 9 define everything here:

  S_B  the thesis's seed list (the first 30 seeds of eval_corpus_2026-05-15.json)
  S_A  the tag's list (the first 30 seeds of eval_corpus.json)

Slot i (0 to 29) is one seed index.  Arm B runs the seed S_B[i] on random-pairs
(holding and find-and-tray-stack at 2, 3 and 4 occluders) and on stack (heights
2, 3 and 4).  Arm A runs S_A[i] on random-pairs and S_B[i] on stack (stack uses
the thesis list in both arms: its cells then line up with the sweep's).  Both
arms: 9 cells a slot, semantic baseline, auto cell size, unit costs off, one
episode a cell.  A job takes two slots (15 jobs); the arm order alternates by
slot parity so a node's load and clock meet both arms alike.
"""

S_B = [0, 2, 4, 15, 16, 19, 20, 25, 28, 34, 36, 39, 42, 43, 44, 45, 48, 50, 53,
       59, 63, 64, 66, 69, 75, 87, 88, 89, 92, 94]
S_A = [0, 2, 5, 7, 10, 15, 16, 17, 18, 19, 21, 22, 24, 25, 26, 29, 33, 34, 38,
       39, 40, 41, 42, 43, 44, 45, 46, 48, 49, 57]
N_SLOTS = 30
SLOTS_PER_JOB = 2
N_JOBS = N_SLOTS // SLOTS_PER_JOB
RP_GOALS = ('holding', 'find-and-tray-stack')
DIFFICULTIES = (2, 3, 4)       # occluders on random-pairs, tower height on stack
ARMS = ('A', 'B')
CAP_S = 1800


def rp_cell(n_occ, seed, goal):
    return dict(scene='random-pairs', n_occluders=n_occ, seed=seed, goal=goal,
                baseline='semantic', unit_costs=False, n_hidden=0)


def stack_cell(height, seed):
    return dict(scene='stack', n_occluders=height, n_targets=3, seed=seed,
                goal='stack', baseline='semantic', unit_costs=False, n_hidden=0)


def slot_seeds(arm, slot):
    """(random-pairs seed, stack seed) of an arm's slot."""
    if arm not in ARMS:
        raise ValueError(f"arm {arm!r}: expected one of {ARMS}")
    if not 0 <= slot < N_SLOTS:
        raise ValueError(f"slot {slot}: expected 0 to {N_SLOTS - 1}")
    return (S_A[slot] if arm == 'A' else S_B[slot]), S_B[slot]


def slot_cells(arm, slot):
    """The nine cells of an arm's slot, in the order they run."""
    rp_seed, stack_seed = slot_seeds(arm, slot)
    cells = [rp_cell(n, rp_seed, g) for n in DIFFICULTIES for g in RP_GOALS]
    cells += [stack_cell(h, stack_seed) for h in DIFFICULTIES]
    return cells


def smoke_cells():
    """The cluster smoke's three cells per arm: the laptop smoke's (PLAN
    section 12): random-pairs 2 occluders seed 2 holding and tray-stack, stack
    height 2 seed 0."""
    return [rp_cell(2, 2, 'holding'), rp_cell(2, 2, 'find-and-tray-stack'),
            stack_cell(2, 0)]


def arm_order(slot):
    """The order the arms run a slot in: A first on even slots, B on odd."""
    return ('A', 'B') if slot % 2 == 0 else ('B', 'A')


def job_slots(job):
    if not 0 <= job < N_JOBS:
        raise ValueError(f"job {job}: expected 0 to {N_JOBS - 1}")
    return tuple(range(job * SLOTS_PER_JOB, (job + 1) * SLOTS_PER_JOB))


def expected_tag(cell):
    """The cell's directory name, the same string both commits' eval_runner
    cell_tag builds for a cell without a cell-size axis (the tests compare)."""
    if cell['scene'] == 'random-pairs':
        return (f"randpairs_occ{cell['n_occluders']}_seed{cell['seed']}"
                f"_{cell['goal']}_uc{int(cell['unit_costs'])}_{cell['baseline']}")
    return (f"occ{cell['n_occluders']}_tgt{cell['n_targets']}_hid{cell['n_hidden']}"
            f"_seed{cell['seed']}_{cell['goal']}_uc{int(cell['unit_costs'])}"
            f"_{cell['baseline']}")


def main(argv=None):
    """For the job script: `p6_slots.py job-slots J` prints the job's slot
    numbers, `p6_slots.py arm-order S` prints the arms in the order a slot runs
    them (one source for the bash and the python)."""
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == 'job-slots':
        print(' '.join(str(s) for s in job_slots(int(argv[1]))))
        return 0
    if len(argv) == 2 and argv[0] == 'arm-order':
        print(' '.join(arm_order(int(argv[1]))))
        return 0
    print(main.__doc__)
    return 2


def as_matrix(cells):
    """The cells as an eval_runner matrix (a list of one-cell sub-matrices, so
    the runner's own iterate_matrix yields them in this order, with n_hidden 0
    as its policy 'none' derives it)."""
    out = []
    for c in cells:
        sub = {'n_occluders': [c['n_occluders']], 'seed': [c['seed']],
               'goal': [c['goal']], 'baseline': [c['baseline']],
               'unit_costs': [c['unit_costs']], 'scene': [c['scene']],
               '_n_hidden_strategy': 'none'}
        if 'n_targets' in c:
            sub['n_targets'] = [c['n_targets']]
        out.append(sub)
    return out


if __name__ == '__main__':
    import sys
    sys.exit(main())
