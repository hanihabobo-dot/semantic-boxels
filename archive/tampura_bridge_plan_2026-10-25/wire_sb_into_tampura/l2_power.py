"""Read-only arithmetic for ARGUMENT.md sections 1.7 and 6 (no file read, no file written).

1. Exact two-sided McNemar (sign test on the discordant pairs) for BF#63 run 2
   as reported (18 vs 9) and for the 20-step re-count (17 vs 10): s101 r1 and
   s139 r1 exceed 20 of TAMPURA's actions with or without observes
   (bf63_step_equiv.txt); TAMPURA succeeded on 101 in both repetitions and
   failed on 139 in both (bf/BF63_gen_scenes/eval2/REPORT.txt:19, 57), so pair
   101 r1 moves from both-succeed to only-TAMPURA and pair 139 r1 from
   only-ours to neither.
2. Power of a pre-registered paired campaign with N new scenes and one
   repetition per arm, IF run 2's discordant share (27 of 76 pairs) and split
   (18 of 27 won by ours) held (an ESTIMATE): D ~ Bin(N, 27/76) discordant
   pairs, X ~ Bin(D, 18/27) won by ours, success = exact two-sided p <= 0.05
   with ours ahead.

Run: python3 -I -B l2_power.py
"""
from math import comb

ALPHA = 0.05
P_DISC = 27 / 76
P_OURS = 18 / 27


def two_sided_p(x, d):
    """Exact two-sided sign test p for x of d discordant pairs."""
    k = min(x, d - x)
    tail = sum(comb(d, i) for i in range(k + 1)) / 2 ** d
    return min(1.0, 2 * tail)


def power(n):
    total = 0.0
    for d in range(1, n + 1):
        pd = comb(n, d) * P_DISC ** d * (1 - P_DISC) ** (n - d)
        if pd < 1e-15:
            continue
        pr = 0.0
        for x in range(d + 1):
            if x > d - x and two_sided_p(x, d) <= ALPHA:
                pr += comb(d, x) * P_OURS ** x * (1 - P_OURS) ** (d - x)
        total += pd * pr
    return total


def main():
    print("1. exact two-sided McNemar on the discordant pairs")
    print(f"   run 2 as reported, ours 18 vs TAMPURA 9: p = {two_sided_p(18, 27):.4f}")
    print(f"   20-step re-count,  ours 17 vs TAMPURA 10: p = {two_sided_p(17, 27):.4f}")
    print("2. power, N new scenes, one repetition per arm, alpha 0.05 two-sided, ours ahead")
    print(f"   assumed: discordant share {P_DISC:.3f}, ours' share of discordant {P_OURS:.3f}")
    for n in (40, 80, 120, 160, 200, 250, 300):
        print(f"   N = {n:3d}: expected discordant {n * P_DISC:5.1f}, power {power(n):.3f}")


if __name__ == "__main__":
    main()
