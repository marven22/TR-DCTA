# BabyAI/MiniGrid held-out evaluation results v1

## Status

The frozen evaluation is complete and independently verified. All 240 held-out
seeds (60–299), 720 paired provenance views, 4,320 executable memory outcomes,
720 donor-context correctness checks, and 123,120 method runs passed integrity
checks. None of the 60 development seeds entered the evaluation.

Fifteen of sixteen preregistered confirmatory claims passed. The only failed
claim was SC-DCTA superiority to hard-source DCTA on *corrupt-memory recall*
under the 67% missing-provenance stress condition. SC-DCTA was significantly
better on the stricter robot-recovery outcome in that same condition.

## SC-DCTA robustness curve

| Missing provenance | Replay budget | Corrupt memories found (of 720) | Robot recoveries (of 240) |
|---:|---:|---:|---:|
| 0% | 2 | 420 | 240 |
| 0% | 4 | 720 | 240 |
| 0% | 8 | 720 | 240 |
| 33% | 2 | 345 | 168 |
| 33% | 4 | 678 | 236 |
| 33% | 8 | 720 | 240 |
| 67% | 2 | 207 | 61 |
| 67% | 4 | 431 | 115 |
| 67% | 8 | 666 | 208 |

The budget interaction replicates development cleanly. Four replays are enough
for near-complete recovery at moderate provenance loss. Under severe loss,
eight replays raise recovery from 115/240 to 208/240.

## Primary budget-4 comparison

| Missing provenance | Method | Corrupt-memory recall | Robot recovery |
|---:|---|---:|---:|
| 33% | SC-DCTA | 94.17% | 236/240 |
| 33% | Probabilistic DCTA | 94.03% | 236/240 |
| 33% | ENS | 95.28% | 236/240 |
| 33% | Hard-source DCTA | 80.42% | 192/240 |
| 33% | Random | 22.31% | 69.18% expected |
| 33% | Known-source reference | 97.50% | 240/240 |
| 67% | SC-DCTA | 59.86% | 115/240 |
| 67% | Probabilistic DCTA | 58.89% | 114/240 |
| 67% | ENS | 60.56% | 115/240 |
| 67% | Hard-source DCTA | 58.19% | 106/240 |
| 67% | Random | 22.16% | 33.10% expected |
| 67% | Known-source reference | 64.03% | 119/240 |

The known-source method knows the corruption origin but not the hidden lineage.
It is a strong information reference, not a mathematical Bayes-optimal upper
bound; under some acquisition metrics another policy can exceed it.

## Confirmatory inference

All effects below are SC-DCTA minus the comparator at budget 4, with paired 95%
bootstrap confidence intervals over 240 held-out seeds.

### Moderate missingness: 33%

- Versus hard-source DCTA, corrupt recall improved by 13.75 points
  [9.72, 18.06] and recovery by 18.33 points [13.33, 23.75]. Both superiority
  claims passed.
- Versus random replay, corrupt recall improved by 71.86 points
  [69.95, 73.69] and recovery by 29.15 points [25.92, 32.45]. Both passed.
- Versus ENS, corrupt recall was 1.11 points lower [-2.22, 0.00] and recovery
  was identical [-1.67, 1.67]. Both passed the frozen 5-point noninferiority
  margin.
- Versus probabilistic DCTA, corrupt recall was 0.14 points higher [0.00, 0.42]
  and recovery was identical. Both noninferiority claims passed.

### Severe missingness: 67%

- Versus hard-source DCTA, corrupt recall was 1.67 points higher
  [-0.97, 4.44], which did **not** establish superiority. Recovery improved by
  3.75 points [0.83, 6.67], which did establish superiority.
- Versus random replay, corrupt recall improved by 37.70 points
  [33.49, 41.81] and recovery by 14.82 points [10.69, 19.12]. Both passed.
- Versus ENS, corrupt recall was 0.69 points lower [-2.36, 0.97] and recovery
  was identical [-2.08, 2.08]. Both noninferiority claims passed.
- Versus probabilistic DCTA, corrupt recall was 0.97 points higher
  [-0.14, 2.22] and recovery was 0.42 points higher [0.00, 1.25]. Both
  noninferiority claims passed.

## Scientific interpretation

The held-out study supports three claims:

1. Retaining source uncertainty is materially better than premature hard
   commitment. The recovery advantage persists under both partial-provenance
   levels and is statistically supported.
2. SC-DCTA is competitive with strong sequential active search. It is
   noninferior to ENS on both acquisition and recovery, but it does not
   outperform ENS in this domain.
3. Missing provenance and replay budget interact exactly as the theory
   predicts: as compatible lineage completions proliferate, more evidence is
   required to separate the harmful chain.

The confidence-aware switch itself contributes only a small incremental gain
over always-probabilistic DCTA in BabyAI: one additional recovery under the
severe mask and nearly identical results elsewhere. Therefore the paper should
not claim that confidence switching dominates probabilistic inference. Its
defensible role is that one fixed method safely commits when the source is
known and otherwise retains uncertainty, while matching the stronger mode
without requiring an externally selected operating regime.

## Paper-facing conclusion

BabyAI is now complete as the exact-inference symbolic domain. The result is
positive but appropriately bounded: SC-DCTA strongly beats random and hard
commitment, is noninferior to ENS and probabilistic DCTA, remains close to the
known-source reference, and exhibits the predicted provenance-budget curve.
MetaWorld remains the continuous-control domain where empirical differentiation
and approximate-posterior scalability must carry the broader performance claim.
