# Meta-World forced-exposure development results

## Design

Every behaviorally harmful descendant in each of the 30 development archives
was used once as a controlled retrieval exposure. The chosen descendant was
placed at rank one for every method, guaranteeing that the pre-audit action
failed. After each frozen four-replay audit, confirmed failed memories were
quarantined and the highest-ranked surviving memory was executed. Non-anchor
memories followed the same MPNet semantic order for every method.

This produced 182 exposure episodes over 10 tasks. This is a conditional stress
test, not an estimate of how frequently ordinary retrieval encounters harmful
memories.

## Main result

| Method | Exposed anchor quarantined | Robot recovered | Recovery after anchor quarantine |
|---|---:|---:|---:|
| SC-DCTA | 101/182 (55.5%) | 93/182 (51.1%) | 93/101 (92.1%) |
| Hard-source DCTA | 101/182 (55.5%) | 93/182 (51.1%) | 93/101 (92.1%) |
| ENS | 100/182 (54.9%) | 92/182 (50.5%) | 92/100 (92.0%) |
| Floored probabilistic DCTA | 100/182 (54.9%) | 92/182 (50.5%) | 92/100 (92.0%) |
| Source-then-DCTA | 95/182 (52.2%) | 87/182 (47.8%) | 87/95 (91.6%) |
| Full-information oracle | 112/182 (61.5%) | 108/182 (59.3%) | 108/112 (96.4%) |

SC-DCTA therefore converted a guaranteed failure into success in approximately
half of the controlled exposures. Its failure decomposition is:

- 81/182: the four-replay budget did not audit the exposed descendant;
- 8/182: the exposed descendant was removed, but the next semantic fallback was
  also behaviorally harmful;
- 93/182: the robot recovered a successful policy.

## Replay-budget curve

The identical 182 exposure episodes were subsequently evaluated at two and
eight replays, with no change to any method or ranking rule.

| Replay budget | SC-DCTA anchor coverage | SC-DCTA robot recovery | Recovery after anchor quarantine |
|---:|---:|---:|---:|
| 2 | 56/182 (30.8%) | 52/182 (28.6%) | 52/56 (92.9%) |
| 4 | 101/182 (55.5%) | 93/182 (51.1%) | 93/101 (92.1%) |
| 8 | 161/182 (88.5%) | 153/182 (84.1%) | 153/161 (95.0%) |

The large monotonic increase confirms that four replays are a material coverage
constraint. Recovery improved by 22.5 percentage points from two to four
replays and by another 33.0 points from four to eight. The gain per added replay
decreased from 11.3 to 8.2 percentage points, suggesting diminishing returns,
but the curve had not fully saturated by eight replays.

At eight replays the comparison remained close: ENS recovered 84.6%, SC-DCTA
84.1%, hard-source DCTA 84.1%, and the full-information oracle 90.7%. These
development differences do not support a superiority claim over ENS or
hard-source DCTA.

## Comparisons

Task-clustered paired bootstrap differences in behavioral recovery:

- SC-DCTA versus ENS: +0.66 percentage points, 95% CI [-1.18, +2.54]; no
  defensible superiority claim.
- SC-DCTA versus floored probabilistic DCTA: +0.63 points, 95% CI [0.00,
  +1.88]; negligible practical separation on development.
- SC-DCTA versus source-then-DCTA: +3.43 points, 95% CI [+1.10, +6.08].
- SC-DCTA versus full-information oracle: -8.22 points, 95% CI [-12.41,
  -4.36], leaving a meaningful ceiling gap.
- SC-DCTA and hard-source DCTA were exactly tied on all 10 development tasks.

## Interpretation

The earlier 0/2 natural-exposure result was a budget-coverage miss: SC-DCTA
quarantined four harmful descendants in each affected archive, but not the
specific fifth harmful descendant that Qwen selected. The larger controlled
study shows that the method does enable behavioral recovery when its audit
reaches the exposed corruption, and quantifies how often that happens under the
four-replay budget.

The result supports a recovery claim but not a development-set superiority
claim over ENS or hard-source DCTA. The natural-incidence and conditional-stress
results should both be retained in a paper because they expose two distinct
bottlenecks: retrieval exposure and finite audit coverage.

## Artifact

- `results/metaworld_forced_exposure_development_evaluation.json`
- `results/metaworld_forced_exposure_development_b2_evaluation.json`
- `results/metaworld_forced_exposure_development_b8_evaluation.json`
