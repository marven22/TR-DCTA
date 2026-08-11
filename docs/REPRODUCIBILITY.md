# Reproducibility guide

## What is and is not stored in Git

Git contains source code, frozen experiment specifications, deterministic seeds,
task/split rules, paper-facing protocols, tests, and compact expected metrics.
It deliberately excludes benchmark downloads, model checkpoints, simulator
caches, prompts/responses at episode scale, and generated JSON ledgers.

The exact paper run can be reproduced in either of two ways:

1. obtain the frozen intermediate-ledger bundle and verify its SHA-256 manifest;
2. regenerate those ledgers from the public benchmarks using the construction
   scripts and then run the same manifest check.

The two paths converge before method execution. TR-DCTA and every comparator
consume the same frozen archive and behavioral ledgers.

## Reference environment

- CPython 3.13.2 was used for the final local execution.
- PyTorch 2.7.0 with CUDA 11.8 was installed on the reference machine.
- NumPy 2.2.4 and sentence-transformers 4.1.0 were used.
- The semantic encoder is pinned to
  `sentence-transformers/all-mpnet-base-v2` revision
  `e8c3b32edf5434bc2275fc9bab85f82640a19130`.
- The full MetaWorld TR-DCTA matrix used 2,048 posterior particles and eight
  worker processes.

Python 3.11 is the supported clean CI target for unit tests. Exact robotics
regeneration should use an environment compatible with the selected upstream
benchmark checkout.

## MetaWorld exact evaluation

### Inputs

The 16 required input artifacts, sizes, and SHA-256 values are listed in
`artifacts/manifest.json`. They contain:

- public and private archive ledgers for development, validation, and test;
- frozen semantic-retrieval and recovery endpoints;
- baseline forced-exposure endpoints;
- the verified 10-task bridge; and
- the independently confirmed BabyAI result that froze the method before the
  full MetaWorld transfer.

Run:

```bash
python scripts/check_artifacts.py --group metaworld-full49
python scripts/run_metaworld_tr_dcta_full49_v1.py \
  --config configs/metaworld_tr_dcta_full49_freeze_v1.json \
  --output results/metaworld_tr_dcta_full49_v1.json --workers 8
python scripts/verify_metaworld_tr_dcta_full49_v1.py \
  --config configs/metaworld_tr_dcta_full49_freeze_v1.json \
  --report results/metaworld_tr_dcta_full49_v1.json \
  --output results/metaworld_tr_dcta_full49_verified_v1.json
python scripts/check_expected_metrics.py \
  --metaworld results/metaworld_tr_dcta_full49_v1.json
```

The runner preserves the original fitting contract:

- development: held-task-out fitting on the other nine development tasks;
- validation: held-task-out fitting on the other 19 development/validation
  tasks; and
- test: one fit using all 20 development/validation tasks and no test tasks.

The verifier independently checks input hashes, replay labels, quarantine
eligibility, replay uniqueness, task/archive/episode counts, sampled behavioral
endpoints, summaries, and task-clustered bootstrap inference.

## BabyAI exact evaluation

The BabyAI reports are larger because they retain every context, provenance
view, method, random replicate, and terminal outcome. They remain external
artifacts.

```bash
python scripts/check_artifacts.py --group babyai
python scripts/run_babyai_unlockpickup_terminal_recovery_heldout_v1.py \
  --config configs/babyai_unlockpickup_terminal_recovery_heldout_freeze_v1.json \
  --output reports/reproduced_unlockpickup.json
python scripts/verify_babyai_unlockpickup_terminal_recovery_heldout_v1.py \
  --config configs/babyai_unlockpickup_terminal_recovery_heldout_freeze_v1.json \
  --report reports/reproduced_unlockpickup.json \
  --output reports/reproduced_unlockpickup_verified.json
```

Use each script's `--help` before execution because the exact CLI is treated as
part of the executable contract. The OpenDoorColor transfer has corresponding
`run_...transfer_v1.py` and `verify_...transfer_v1.py` commands.

## End-to-end ledger reconstruction

The included construction scripts preserve the actual research pipeline:

1. build the benchmark task population and fixed split identities;
2. execute clean and corrupted policies in the simulator;
3. construct symbolic memory archives and source rotations;
4. mask provenance using frozen seeds;
5. fit source and cascade models using only the permitted split;
6. build observable and private recovery ledgers;
7. reconstruct forced-exposure retrieval endpoints;
8. run baselines and TR-DCTA; and
9. aggregate and independently verify the result.

Important entry points include:

- `build_prob_dcta_publication_v2_population.py`
- `run_prob_dcta_publication_v2_generate.py`
- `combine_prob_dcta_publication_v2_generation.py`
- `build_prob_dcta_publication_v2_ledgers.py`
- `build_prob_dcta_metaworld_mask_consistent_ledgers.py`
- `build_metaworld_recovery_manifests.py`
- `run_metaworld_recovery_events.py`
- `evaluate_metaworld_recovery.py`
- `evaluate_metaworld_forced_exposure.py`
- `run_sc_dcta_metaworld_baselines.py`

These stages are intentionally not collapsed into a silent monolithic script:
public/private separation and hashes at each boundary are part of the audit
design. Before public release, a clean Linux reconstruction must be performed
and its exact command transcript added here.

## Statistical unit

The task is the inferential cluster. Source rotations and forced-exposure
episodes within a task are not treated as independent tasks. Confidence
intervals use the frozen paired task-clustered bootstrap seeds recorded in the
configurations.

## Failure policy

Do not bypass a hash mismatch. A mismatch means the experiment is no longer the
frozen paper run. Regenerate the downstream artifacts under a new protocol
identifier or obtain the correct archived bundle.

