# Meta-World missing-provenance failure-strata results

## Result

The frozen diagnostic paired all 565 held-out harmful-descendant episodes
between complete provenance and 50% missing provenance at budget four. It did
not modify or rerun SC-DCTA.

The initial hypothesis that deep descendants explain most loss is not
supported. The clearest concentration of loss is instead in descendants with
only one source ancestor and in small affected cascades, both of which provide
less redundant evidence when formation edges disappear.

## Held-out strata

| Stratum | Episodes | SC-DCTA recovered at 0% | Recovered at 50% | Task-macro change |
|---|---:|---:|---:|---:|
| Observed path remains connected | 134 | 76 | 80 | -0.75 pp [-9.08, +7.41] |
| Observed path disconnected | 431 | 223 | 202 | -5.08 pp [-8.31, -2.11] |
| Shallow depth 1–2 | 332 | 197 | 180 | -5.24 pp [-9.21, -1.17] |
| Deep depth 3+ | 233 | 102 | 102 | +0.08 pp [-6.21, +6.06] |
| Single-source ancestry | 301 | 177 | 150 | -9.02 pp [-13.51, -4.63] |
| Multi-source ancestry | 264 | 122 | 132 | +3.27 pp [-2.46, +8.80] |
| Small cascade, at most 6 | 143 | 126 | 112 | -9.95 pp [-17.93, -2.56] |
| Large cascade, more than 6 | 422 | 173 | 170 | -0.60 pp [-1.37, 0.00] |

Within SC-DCTA, the paired multi-source-minus-single-source change is +12.29
points, interval [+3.30, +21.53]. The large-minus-small-cascade change is +9.35
points, interval [+2.11, +17.24]. These are the strongest mechanistic
diagnostics.

Disconnected descendants lost more recovery than connected descendants, but
the paired difference between those two strata was imprecise: -4.33 points,
interval [-14.60, +5.71]. The result is directionally consistent with broken
paths but not independently decisive.

## Source uncertainty

High-confidence source cases contained 525 episodes across 27 test tasks and
declined by 2.40 points. Low-confidence cases contained only 40 episodes across
three tasks and declined by 8.89 points, but the interval included zero. Only
one test task contained a top-1 source error. Source-confidence and source-error
strata are therefore too small for a strong inferential claim.

## SC-DCTA versus ENS mechanism

For disconnected descendants, SC-DCTA and ENS degraded similarly: the
SC-minus-ENS change was -0.22 points, interval [-2.55, +1.95]. The overall ENS
robustness advantage does not arise because ENS uniquely solves disconnected
lineage. Instead, ENS gains recovery on the subset whose source path remains
connected after masking, while SC-DCTA is approximately stable there. This is
a redistribution of acquisition choices under the changed posterior, not
evidence that hidden edges help ENS causally.

## Interpretation

Missing provenance is most damaging when an affected memory has a single line
of support. Shared descendants with multiple source ancestors retain redundant
signals even after half of the formation edges are hidden. Similarly, large
cascades leave many correlated indicators, whereas a small cascade can lose
most of its visible evidence after only a few edge removals.

The correct mechanistic statement is:

> SC-DCTA's missing-provenance weakness is primarily an evidence-redundancy
> problem, not a simple cascade-depth problem.

This diagnostic may motivate a future latent-edge or path-redundancy extension,
but that extension cannot be validated on the already-inspected Meta-World
test set.

## Artifacts

- Protocol: `docs/SC_DCTA_METAWORLD_FAILURE_STRATA_PROTOCOL.md`
- Result ledger: `results/metaworld_failure_strata.json`
- Analysis: `scripts/analyze_metaworld_failure_strata.py`
