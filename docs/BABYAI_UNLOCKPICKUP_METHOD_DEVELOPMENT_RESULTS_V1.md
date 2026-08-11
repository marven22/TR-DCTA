# BabyAI UnlockPickup method-development results v1

## Status

**Verified NO-GO for confirmatory held-out testing under the current SC-DCTA freeze.**

The run completed without simulator, labeling, grid, or accounting errors. The
independent verifier reproduced every gate and primary metric. The held-out
seeds (60--299) remain unopened.

## Experiment

- Environment: `BabyAI-UnlockPickupDist-v0`
- Development contexts: 60 seeds (0--59)
- Executable memories: 1,080 (18 per context)
- Provenance views: 180 (complete, 33% missing, 67% missing)
- Replay budgets: 2, 4, and 8
- Methods: 10 deterministic methods plus 50 random replicates
- Total method runs: 32,400
- True cascade lengths: 20 each of one, two, and three affected stages
- Primary endpoint: the 120 partial-provenance views at budget 4

## Primary result

| Method | Weighted harmful-memory recall | Robot recovery | Recovery count |
|---|---:|---:|---:|
| SC-DCTA | 0.7139 | 0.7667 | 92 / 120 |
| ENS | 0.8139 | 0.8333 | 100 / 120 |
| Prob-DCTA | 0.6903 | 0.7583 | 91 / 120 |
| Hard-source DCTA | 0.7083 | 0.7250 | 87 / 120 |
| Random | 0.2152 | 0.5750 | mean 69 / 120 |
| Oracle source | 0.8000 | 0.8333 | 100 / 120 |
| Full-information hindsight | 1.0000 | 1.0000 | 120 / 120 |

The frozen 0.05 noninferiority margin was not met. SC-DCTA trailed ENS by
0.1000 weighted-recall points and 0.0667 recovery points. SC-DCTA did beat
random by a large margin.

## Interpretation

This is not an environment failure. Every intended corrupted memory failed in
the simulator, every clean memory succeeded, all replay labels matched those
executions, and sampled executions reproduced exactly.

The longer stochastic cascade exposes an objective mismatch. SC-DCTA chooses
between hard and probabilistic *myopic risk* policies using expected discovered
harm. ENS uses the remaining replay budget to look ahead. When cascade length
and provenance links are both uncertain, ENS's budget-level look-ahead finds a
better set of diagnostic replays. The gap is concentrated in partial
provenance, especially the 67%-missing condition and ambiguous or misleading
source priors.

## Decision

Do not run the current method on held-out UnlockPickup seeds. Doing so after a
failed development gate would spend confirmatory data on a method already known
not to satisfy the frozen criterion. The defensible next step is to specify a
single decision-theoretic extension on development data that optimizes terminal
quarantine/recovery under a fixed replay budget. Only after that extension and
its gate are frozen should the untouched held-out seeds be opened.

## Immutable artifacts

- Development report SHA-256:
  `7c4d6125e3bbd05065575dbdc391a1717c4b5c1a77523acdfdb8dccea4bb5c18`
- Report: `reports/babyai_unlockpickup_method_development_v1.json`
- Independent verification:
  `reports/babyai_unlockpickup_method_development_verified_v1.json`
