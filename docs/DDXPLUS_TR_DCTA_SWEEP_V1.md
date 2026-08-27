# DDXPlus TR-DCTA budget and provenance sweep v1

Every cell is the 26-task DDXPlus test split, 284 forced-exposure episodes, and
2,048 particles. The frozen primary condition is budget 4 at 25% missing
provenance; the remaining cells are declared sweep cells and are recorded as
such in their reports.

| Missing provenance | Budget | TR-DCTA | SC-DCTA | ENS | Full-information comparator |
|---:|---:|---:|---:|---:|---:|
| 0% | 2 | **134/284** | 82/284 | 93/284 | 130/284 |
| 0% | 4 | **241/284** | 169/284 | 180/284 | 241/284 |
| 25% | 2 | **134/284** | 72/284 | 82/284 | 130/284 |
| 25% **(primary)** | 4 | **231/284** | 155/284 | 164/284 | 241/284 |
| 50% | 2 | **133/284** | 52/284 | 69/284 | 130/284 |
| 50% | 4 | **242/284** | 126/284 | 143/284 | 241/284 |

### Task-clustered paired inference

| Missing provenance | Budget | TR-DCTA minus SC-DCTA | TR-DCTA minus ENS | Wins/ties/losses vs SC-DCTA |
|---:|---:|---:|---:|---:|
| 0% | 2 | +0.2158 [+0.1425, +0.2923] | +0.1634 [+0.1073, +0.2232] | 19 / 7 / 0 |
| 0% | 4 | +0.2433 [+0.1739, +0.3166] | +0.2147 [+0.1570, +0.2762] | 22 / 4 / 0 |
| 25% | 2 | +0.2520 [+0.1788, +0.3346] | +0.2024 [+0.1408, +0.2696] | 24 / 2 / 0 |
| 25% | 4 | +0.2682 [+0.1962, +0.3476] | +0.2393 [+0.1799, +0.3050] | 23 / 3 / 0 |
| 50% | 2 | +0.3292 [+0.2451, +0.4170] | +0.2546 [+0.1820, +0.3349] | 23 / 3 / 0 |
| 50% | 4 | +0.4115 [+0.3335, +0.4890] | +0.3475 [+0.2676, +0.4290] | 25 / 1 / 0 |

TR-DCTA wins every cell, every interval excludes zero, and it loses no test task
in any configuration.

### The advantage grows as provenance degrades

At budget 4, TR-DCTA is nearly flat across provenance conditions while SC-DCTA
falls away, so the margin widens from +0.2433 to +0.4115:

| Method | 0% hidden | 25% hidden | 50% hidden |
|---|---:|---:|---:|
| TR-DCTA | 241 | 231 | 242 |
| SC-DCTA | 169 | 155 | 126 |
| TR-DCTA minus SC-DCTA | +0.2433 | +0.2682 | +0.4115 |

The frozen primary condition is the middle of this range rather than the most
favourable one.

### Two observations that require qualification

1. **TR-DCTA exceeds the full-information comparator in two cells** — 242/284
   against 241/284 at budget 4 with 50% missing provenance, and 134/284 against
   130/284 at budget 2 with complete provenance. That comparator is given the
   realized affected set and replays it
   in identifier order; under a replay budget smaller than the affected set it
   can confirm memories that do not govern the retrieval outcome. As in the
   Meta-World study it is a strong reference comparator, not a proof of the
   globally optimal terminal-recovery ceiling.

2. **TR-DCTA is non-monotonic in missing provenance** at budget 4, recovering
   241, then 231, then 242 episodes. The realized harmful sets are identical
   across mask rates, which change only what the auditor can observe,
   so the dip at 25% is not explained by a change in the underlying task. The
   effect is 11 of 284 episodes and the pipeline is deterministic, so it is not
   sampling variation. This is unexplained and is recorded here as an open item.

### Provenance of these numbers

These cells were produced from the DDXPlus Qwen generation that predates the
donor-description fix, in which one task of 44 carried a corrupted memory whose
text was identical to a safe one. They are indicative and must be regenerated
against the corrected archives before publication.
