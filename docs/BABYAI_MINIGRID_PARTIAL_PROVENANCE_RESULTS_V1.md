# BabyAI/MiniGrid partial-provenance results v1

## Outcome

The experiment is complete and independently verified. The frozen aggregate
decision is **NO_GO** because SC-DCTA recovered 83/120 partial-provenance views
at budget 4, below the preregistered 80% threshold (96/120). This should not be
silently relabeled after observing the data.

The result nevertheless reveals a useful and coherent robustness curve. At 33%
missing provenance, four replays are nearly sufficient. At 67% missing
provenance, four replays are information-limited for every method, including the
known-source oracle; eight replays restore most performance.

## Executed matrix

- 60 fixed executable BabyAI archives
- three paired provenance views per archive: 0%, 33%, and 67% links hidden
- 180 archive-provenance views
- exact enumeration of 1, 8, or 13,824 consistent lineage completions
- 3,780 structured method runs
- 27,000 random-baseline runs
- 30,780 total method runs
- replay budgets 2, 4, and 8

All replay labels came from the previously frozen and environment-verified
memory executions. Candidate identifiers were opaque, and methods did not
receive the private lineage completion.

## SC-DCTA robustness

| Missing provenance | Budget | Corrupt memories found (of 180) | Correctly quarantined corrupt memories (of 180) | Robot recoveries (of 60) |
|---:|---:|---:|---:|---:|
| 0% | 2 | 105 | 180 | 60 |
| 0% | 4 | 180 | 180 | 60 |
| 0% | 8 | 180 | 180 | 60 |
| 33% | 2 | 91 | 162 | 44 |
| 33% | 4 | 167 | 177 | 57 |
| 33% | 8 | 180 | 180 | 60 |
| 67% | 2 | 56 | 102 | 10 |
| 67% | 4 | 116 | 137 | 26 |
| 67% | 8 | 171 | 174 | 54 |

Recovery is deliberately strict: all three harmful memories must be among the
three quarantined memories. Finding or removing two of three improves the
recall metrics but does not count as robot recovery because one forced harmful
retrieval remains possible.

## Budget-4 method comparison

| Missing provenance | Method | Corrupt memories found (of 180) | Robot recoveries (of 60) |
|---:|---|---:|---:|
| 33% | SC-DCTA | 167 | 57 |
| 33% | Probabilistic DCTA | 167 | 57 |
| 33% | ENS | 172 | 59 |
| 33% | Hard-source DCTA | 141 | 46 |
| 33% | Oracle source | 175 | 60 |
| 67% | SC-DCTA | 116 | 26 |
| 67% | Probabilistic DCTA | 113 | 26 |
| 67% | ENS | 107 | 22 |
| 67% | Hard-source DCTA | 103 | 22 |
| 67% | Oracle source | 120 | 27 |

Across both partial conditions, SC-DCTA found 283/360 corrupted memories, ENS
found 279/360, and random replay averaged 0.669 of three corrupted memories per
archive. SC-DCTA recovered 83/120 paired views and ENS recovered 81/120.

These small aggregate differences are descriptive development results, not a
statistically supported superiority claim. ENS is slightly stronger under 33%
missingness; SC-DCTA is stronger under 67% missingness.

## What the result means

First, partial provenance is a real difficulty axis rather than a cosmetic
mask. With 67% of links hidden, the graph permits 13,824 lineage completions.
Knowing the true source alone does not reveal its three descendants: the oracle
recovers only 27/60 archives with four replays. SC-DCTA reaches 26/60, very near
that ceiling.

Second, the failure at four replays is primarily an evidence-budget limitation,
not collapse of the method. Raising the budget to eight increases severe-mask
SC-DCTA recovery from 26/60 to 54/60; the oracle reaches 55/60. Under 33%
missingness, eight replays yield 60/60 recovery.

Third, the confidence-aware mechanism produces a modest benefit in the most
ambiguous condition: SC-DCTA finds 116 corrupted descendants under 67%
missingness at budget 4, versus 113 for always-probabilistic DCTA and 103 for
hard-source DCTA. It does not differentiate itself under moderate missingness.

## Paper-facing recommendation

Do not discard the experiment, and do not claim that SC-DCTA solves arbitrary
provenance loss. Report the 0/33/67% degradation curve and the budget interaction
as a robustness result. The clean claim is:

> SC-DCTA remains near the known-source ceiling as provenance ambiguity grows;
> recovery depends jointly on lineage observability and replay budget.

For a held-out BabyAI panel, retain all three provenance conditions and budgets.
Treat 33% missingness at budget 4 as the practical operating point and 67%
missingness as an explicit stress regime. The frozen `NO_GO` means the current
four-replay configuration does not justify promising 80% recovery averaged
across both partial conditions; it does not invalidate the robustness finding.
