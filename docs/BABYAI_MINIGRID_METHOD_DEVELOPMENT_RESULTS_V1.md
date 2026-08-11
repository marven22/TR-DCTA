# BabyAI/MiniGrid method-development results v1

## Verdict

The frozen development decision is **GO**, and the artifact independently
verifies. SC-DCTA is effective in this executable symbolic domain, including
when the prior points to the wrong source. However, this first construction is
not difficult enough to separate SC-DCTA from probabilistic DCTA or ENS. It
supports cross-domain validity and the value of retaining source uncertainty;
it does not yet support a claim of acquisition superiority over ENS.

## Executed scope

- 60 BabyAI target contexts and 60 independently formed archives
- 18 memories per archive: six source lineages with three descendants each
- 1,080 target-context memory executions
- 180 donor-context checks establishing that harmful memories were locally
  correct before transfer
- 1,260 structured method runs
- 9,000 random-baseline runs (50 replicates per archive-budget cell)
- replay budgets 2, 4, and 8
- zero execution errors

All three descendants of the designated corrupted family failed on their
target context. All 15 clean memories in every archive succeeded. Twelve fixed
environment executions were repeated independently and matched in success,
reward, and step count.

## Main result

| Method | Budget 2: corrupt memories found (of 180) | Budget 4 | Budget 8 | Recovery at budget 2 | Recovery at budget 4 |
|---|---:|---:|---:|---:|---:|
| SC-DCTA | 105 | 180 | 180 | 60/60 | 60/60 |
| Probabilistic DCTA | 105 | 180 | 180 | 60/60 | 60/60 |
| ENS | 105 | 180 | 180 | 60/60 | 60/60 |
| Hard-source DCTA | 90 | 142 | 156 | 45/60 | 45/60 |
| Source information gain | 59 | 78 | 112 | 60/60 | 60/60 |
| Static risk | 75 | 135 | 180 | 45/60 | 45/60 |
| Oracle source | 120 | 180 | 180 | 60/60 | 60/60 |

Random replay is averaged over 50 replicates. At budget 4 it found 1,950 of
9,000 available corrupted descendants across the replicated archive runs, or
0.65 of three per archive. SC-DCTA found all three in every archive.

SC-DCTA chose hard mode for the 45 known-source archive-budget cells and
probabilistic mode for the remaining 135 cells. This is the intended behavior:
it commits only when the source is actually known.

## Most informative stratum

The 15 misleading-prior archives supplied a decoy source with probability 0.55
and the true source with probability 0.25. At budget 2:

- SC-DCTA and ENS found one of three corrupted descendants in every archive,
  inferred the true source in 15/15 archives, and recovered the robot in 15/15;
- hard-source DCTA found none, inferred the wrong source in 15/15, and recovered
  in 0/15.

At budget 4, SC-DCTA and ENS found all three corrupted descendants and recovered
in 15/15, while hard-source DCTA found seven of the 45 corrupted descendants
and still recovered in 0/15.

This is strong evidence for the paper's uncertainty claim: premature source
commitment can preserve the harmful lineage, whereas full posterior updating
can reverse misleading initial evidence.

## Honest limitation and next decision

The binary replay evidence and three-member lineages make source elimination
very clean. SC-DCTA, probabilistic DCTA, and ENS therefore reach the same
ceiling. Scaling this exact construction from 60 to 240 contexts would produce
more precise evidence for a tie, not a more discriminating experiment.

Before a held-out scale-up, the next useful BabyAI experiment should introduce
one preregistered, theory-aligned difficulty axis—partial provenance is the
natural choice—while preserving executable labels and the same methods and
budgets. If SC-DCTA remains effective and distinguishes itself under incomplete
lineage information, then a held-out panel is justified. If all posterior-aware
methods remain tied, BabyAI should be reported as a compact cross-domain
validation rather than a second flagship benchmark.
