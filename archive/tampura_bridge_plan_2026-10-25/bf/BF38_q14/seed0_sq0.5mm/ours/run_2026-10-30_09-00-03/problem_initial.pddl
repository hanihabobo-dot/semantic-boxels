;; Auto-generated problem file from PDDLStreamPlanner.export_problem_pddl()
;; Static init state only — stream-certified facts are NOT included.

(define (problem boxel-tamp-debug)
  (:domain boxel-tamp)

  (:objects
    d_cups_ud
    dice
    free_000
    free_001
    free_002
    free_003
    free_004
    free_005
    home
    q_home
    shadow_of_d_cups_ud
  )

  (:init
    (Boxel d_cups_ud)
    (Boxel free_000)
    (Boxel free_001)
    (Boxel free_002)
    (Boxel free_003)
    (Boxel free_004)
    (Boxel free_005)
    (Boxel home)
    (Boxel shadow_of_d_cups_ud)
    (Config q_home)
    (Obj d_cups_ud)
    (Obj dice)
    (at_config q_home)
    (blocks_view_at d_cups_ud d_cups_ud shadow_of_d_cups_ud)
    (blocks_view_at d_cups_ud free_001 shadow_of_d_cups_ud)
    (blocks_view_at d_cups_ud free_002 shadow_of_d_cups_ud)
    (blocks_view_at d_cups_ud free_005 shadow_of_d_cups_ud)
    (boxel_fits d_cups_ud free_000)
    (boxel_fits d_cups_ud free_001)
    (boxel_fits d_cups_ud free_002)
    (boxel_fits d_cups_ud free_003)
    (boxel_fits d_cups_ud free_005)
    (boxel_fits d_cups_ud shadow_of_d_cups_ud)
    (boxel_fits dice free_000)
    (boxel_fits dice free_001)
    (boxel_fits dice free_002)
    (boxel_fits dice free_003)
    (boxel_fits dice free_004)
    (boxel_fits dice free_005)
    (boxel_fits dice shadow_of_d_cups_ud)
    (clear d_cups_ud)
    (clear dice)
    (config_for_boxel q_home home)
    (handempty)
    (is_free_space free_000)
    (is_free_space free_001)
    (is_free_space free_002)
    (is_free_space free_003)
    (is_free_space free_004)
    (is_free_space free_005)
    (is_object d_cups_ud)
    (is_shadow shadow_of_d_cups_ud)
    (obj_at_boxel d_cups_ud d_cups_ud)
    (obj_at_boxel_KIF d_cups_ud d_cups_ud)
    (obj_at_boxel_KIF d_cups_ud shadow_of_d_cups_ud)
    (obj_at_boxel_KIF dice d_cups_ud)
    (obj_at_boxel_KIF dice free_000)
    (obj_at_boxel_KIF dice free_001)
    (obj_at_boxel_KIF dice free_002)
    (obj_at_boxel_KIF dice free_003)
    (obj_at_boxel_KIF dice free_004)
    (obj_at_boxel_KIF dice free_005)
    (on_surface free_000)
    (on_surface free_001)
    (on_surface free_003)
    (on_surface free_004)
    (on_surface free_005)
    (on_table d_cups_ud)
    (on_table dice)
  )

  (:goal (and (holding dice) (at_config q_home)))
)
