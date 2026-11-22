"""Goals of an episode: the goal test the loop asks after every round, and
the builder of a stack goal.

test_full_pipeline imports every name of this file, and callers import
them from there.
"""
import random


def goal_satisfied(goal, on_relations=None, target_found=False) -> bool:
    """
    Generic goal-predicate evaluator for the orchestration loop (audit #30).

    Decoupled from BeliefState because stack goals don't need a belief
    state at all — there are no shadows.  Heads we support:

      ('holding', obj)    — delegates to ``target_found`` (set by the
                            pick handler / sense outcome).
      ('on', a, b)        — checked against ``on_relations``, the
                            planner-side picture of the live stack
                            maintained by the stack action handler.
      ('on_table', obj)   — true iff ``obj`` is not a key in
                            ``on_relations`` (audit #41).  Consulted
                            only at replan boundaries where (handempty)
                            holds, so held cubes never confound this.
      ('and', g1, g2,..)  — conjunction; recurses.

    Reading from ``on_relations`` rather than re-deriving from PyBullet
    AABBs each tick avoids races with in-flight settling — by the time
    the loop polls, execute_stack has already let physics settle and
    written the canonical relation.
    """
    on_relations = on_relations or {}
    if not isinstance(goal, tuple):
        return False
    head = goal[0]
    if head == 'and':
        return all(goal_satisfied(sub, on_relations, target_found)
                   for sub in goal[1:])
    if head == 'holding':
        return target_found
    if head == 'on':
        a, b = str(goal[1]), str(goal[2])
        return on_relations.get(a) == b
    if head == 'on_table':
        # audit #41 — symbolic mirror.  An object is "on the table" iff
        # it is not stacked on another cube.  Held objects are absent
        # from on_relations as keys but goal_satisfied is only consulted
        # at replan boundaries (handempty), so this is sound.
        return str(goal[1]) not in on_relations
    return False


def build_stack_goal(stackable_objects, stack_height, rng=None):
    """
    Pick ``stack_height`` distinct objects from ``stackable_objects`` and
    return a goal for a tower of that height (audit #30).

    For height H the goal is::

        ('and', ('on', t_1, t_2), ..., ('on', t_{H-1}, t_H),
                ('on_table', t_H))

    where ``t_1`` is the top and ``t_H`` is the base.  The
    ``on_table`` clause (audit #41) makes the table-resting base
    explicit so the verifier can rule out floating-tower
    interpretations.

    Args:
        stackable_objects: Object IDs the planner may use as cubes.
        stack_height: Total cubes in the stack (>= 2).  Height 1 is
            rejected because it collapses to (clear t), which the
            planner trivially satisfies — use --goal holding instead.
        rng: ``random.Random`` for reproducible shuffling.  Defaults to
            module ``random`` so the existing --seed plumbing keeps
            working unchanged.
    """
    if stack_height < 2:
        raise ValueError(
            f"--stack-height must be >= 2 for a meaningful goal "
            f"(got {stack_height}).  Use --goal holding for a single object."
        )
    if len(stackable_objects) < stack_height:
        raise ValueError(
            f"Need at least {stack_height} stackable objects for "
            f"--stack-height={stack_height}, have {len(stackable_objects)}. "
            f"Increase --n-objects."
        )

    rng = rng or random
    chosen = list(stackable_objects)
    rng.shuffle(chosen)
    chosen = chosen[:stack_height]

    pairs = [('on', chosen[i], chosen[i + 1])
             for i in range(stack_height - 1)]
    base = chosen[-1]                        # t_H — the cube at the bottom
    clauses = pairs + [('on_table', base)]   # audit #41 — ground the tower
    return ('and',) + tuple(clauses)
