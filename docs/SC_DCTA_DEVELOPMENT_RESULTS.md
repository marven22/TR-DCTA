# SC-DCTA Meta-World Development Results

## Decision

SC-DCTA passes all six predeclared development gates.  Freeze it as the single
proposed method for the next held-out evaluation.  Treat hard-source DCTA and
the original floored Prob-DCTA as ablations, not as selectable operating modes.

This is a development-set decision, not a test-set claim.

## What changed

The old probabilistic implementation used a probability floor both to ensure
that every possible source was sampled and as the agent's source belief.  The
floor therefore made confident beliefs artificially uncertain.

SC-DCTA separates those two roles.  If `p(s)` is the calibrated belief that
source `s` is corrupt, particles are sampled from the support-safe proposal

`q(s) = 0.05 + 0.85 p(s)`

in a three-source archive.  A particle drawn from source `s` is then weighted
by `p(s) / q(s)`.  The proposal explores every source, while the weighted
posterior still represents `p`.  Existing probabilistic DCTA risk acquisition
then chooses the four replays.  There is no confidence threshold or hard/prob
mode switch.

## Protocol

- Domain: Meta-World.
- Data: 10 development tasks, 3 rotations, and 3 provenance-mask levels.
- Primary condition: 30 archives at budget 4 and 25% missing provenance.
- Sensitivity conditions: budgets 2, 4, and 8 crossed with 0%, 25%, and 50%
  missing provenance (90 archives).
- Fitting: leave one task out; the evaluated task never contributes labels to
  its source or cascade calibrator.
- Posterior: 2,048 particles with deterministic seeds.
- Inputs: citation-consistent public ledgers only; 616 citations revealing
  masked edges were redacted.

## Primary result

| Method | Weighted harmful-memory recall |
|---|---:|
| SC-DCTA | **0.6497** |
| Hard-source DCTA | **0.6497** |
| Known-source DCTA | **0.6497** |
| SC-ENS | 0.6398 |
| Original floored Prob-DCTA | 0.6384 |
| Source-then-DCTA | 0.6136 |
| Full-information oracle | 0.7484 |

SC-DCTA improved over the original floored Prob-DCTA by 0.0113.  The
task-clustered 95% interval was `[0.0000, 0.0339]`: one task improved and nine
tied.  It exceeded SC-ENS by 0.0098, although that comparison is uncertain
(`95% CI [-0.0140, 0.0346]`; six task wins, three ties, and one loss).

SC-DCTA exactly matched hard-source and known-source DCTA in the primary
condition.  This happened naturally from the posterior and acquisition rule;
SC-DCTA did not switch to a separately chosen hard mode.

## Calibration and sampling checks

| Quantity | Result |
|---|---:|
| Target source Brier score | 0.0639 |
| Original floored-posterior Brier score | 0.0944 |
| Importance-corrected particle Brier score | 0.0648 |
| Mean L1 error from target belief | 0.0083 |
| Mean effective sample fraction | 0.9438 |
| Worst effective sample fraction | 0.8931 |

The importance correction removed almost all distortion introduced by the
sampling floor while retaining many effective particles.

An independently seeded 8,192-particle replication also passed every frozen
stability threshold across the 30 primary archives:

- mean marginal absolute difference: 0.0056;
- worst marginal absolute difference: 0.0364;
- worst source-probability difference: 0.0204; and
- mean weighted-recall absolute difference: 0.0163.

The exact replay sequence agreed in 73.3% of archives.  Near-tied replay
choices can therefore move, but the aggregate conclusions were stable under a
fourfold particle increase.

## Sensitivity result

SC-DCTA versus original floored Prob-DCTA, reported as weighted recall:

| Replay budget | 0% missing | 25% missing | 50% missing |
|---:|---:|---:|---:|
| 2 | 0.4153 / 0.4153 | 0.3934 / 0.3732 | 0.3781 / 0.3743 |
| 4 | 0.6890 / 0.6890 | 0.6497 / 0.6384 | 0.6550 / 0.6398 |
| 8 | 0.9167 / 0.9167 | 0.9145 / 0.9145 | 0.9300 / 0.9035 |

SC-DCTA was never worse than the floored implementation in these nine cells.
It was sometimes below hard-source DCTA, particularly at budget 2, but never
by enough to fail the predeclared robustness gate.

## Honest limitation

Only 3 of the 30 primary archives had maximum source probability below 0.8.
In those three archives, SC-DCTA, floored Prob-DCTA, hard-source DCTA, and
known-source DCTA all selected equivalently and obtained 0.5238 recall.  The
development evidence therefore shows that SC-DCTA avoids the old
over-conservatism without sacrificing performance.  It does **not** yet show
that probabilistic reasoning wins when the source is genuinely ambiguous.

The held-out evaluation must preserve this distinction.  A defensible claim is
that SC-DCTA is a coherent, calibrated single method whose high-confidence
behavior approaches hard-source DCTA.  An uncertainty-protection claim requires
enough naturally ambiguous held-out cases or a separately predeclared stress
test.

## Gate audit

All frozen gates passed:

1. within 0.01 of the better hard/floored constituent;
2. lower initial source Brier score than the floored posterior;
3. within 0.03 of SC-ENS;
4. at least 85% of known-source performance;
5. no sensitivity cell more than 0.03 below both constituents; and
6. effective sample fraction at least 0.50 in every archive.

## Reproducibility

- Main result: `results/sc_dcta_metaworld_development.json`
- Particle validation: `results/sc_dcta_particle_validation.json`
- Development runner: `scripts/run_sc_dcta_metaworld_development.py`
- Particle validator: `scripts/validate_sc_dcta_particles.py`
- Frozen protocol: `docs/SC_DCTA_DEVELOPMENT_PROTOCOL.md`
- Particle protocol: `docs/SC_DCTA_PARTICLE_VALIDATION_PROTOCOL.md`

The complete automated test suite passes: 161 tests.
