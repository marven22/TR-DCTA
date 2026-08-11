# TR-DCTA

Reproducibility code for **Terminal-Recovery Dynamic Causal Trajectory
Auditing (TR-DCTA)**, a budgeted audit policy for persistent agent-memory
corruption under incomplete provenance.

TR-DCTA chooses physical memory replays by their expected effect on the final
quarantine-and-recovery decision. This differs from discovery-oriented methods
that optimize the number or weighted mass of harmful memories found during the
audit. The repository contains the frozen TR-DCTA implementation, matched
baselines, MetaWorld and BabyAI evaluation pipelines, independent verifiers,
theory code, and compact expected metrics.

> **Release-candidate status.** This directory is a local publication artifact
> prepared for review before upload. A code license, complete author list,
> archival artifact URL, and paper citation must be finalized before the public
> release. See `RELEASE_CHECKLIST.md`.

## Headline evaluations

| Domain | Evaluation unit | TR-DCTA | SC-DCTA | ENS–SharedPosterior | Full-information reference |
|---|---:|---:|---:|---:|---:|
| MetaWorld test | 565 forced-exposure episodes across 29 tasks | **322** | 289 | 287 | 325 |
| BabyAI UnlockPickup | 240 held-out contexts, partial provenance, budget 4 | **0.8875** | 0.8333 | 0.8646 | 1.0000 |

Exact expected counts, intervals, and artifact hashes are stored in
`expected/paper_metrics_v1.json` and `artifacts/manifest.json`. Raw datasets,
model checkpoints, simulator caches, and episode-level outputs are deliberately
not committed.

## Repository map

```text
configs/       Frozen experimental configurations and seeds
docs/          Theory, protocols, results summaries, and provenance records
expected/      Compact expected paper metrics (not raw results)
artifacts/     SHA-256 manifest for large generated ledgers
scripts/       Construction, execution, aggregation, and verification commands
src/mcx/       TR-DCTA, DCTA family, posterior models, and baseline code
tests/         Unit tests and deterministic smoke tests
```

## Reproducibility levels

### 1. Code and theory smoke test

This path requires no benchmark downloads and verifies the acquisition logic,
terminal objective, posterior conditioning, baselines, and theory utilities.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements/core.txt
python -m pip install -e .
python -m pytest -q
```

### 2. Exact evaluation from frozen ledgers

Large intermediate ledgers are kept outside Git. Place them at the paths in
`artifacts/manifest.json`, then verify every byte before running:

```bash
python scripts/check_artifacts.py --manifest artifacts/manifest.json
```

Run and independently verify the full MetaWorld matrix:

```bash
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

Compact BabyAI expectations can likewise be checked with
`--babyai-unlockpickup` and `--babyai-opendoorcolor` after producing or
downloading those reports.

The frozen full-49 run contains 49 tasks, 147 archives, and 919 forced-exposure
episodes. On the reference Windows/CUDA system it required approximately 83
seconds after the ledgers were available.

### 3. End-to-end reconstruction from public benchmarks

This path regenerates benchmark episodes, policies, archives, provenance masks,
posteriors, and recovery ledgers. It requires the upstream robotics environments
and substantially more compute. See `docs/REPRODUCIBILITY.md` and
`docs/DATASETS.md`. Dataset files are never required to be committed to this
repository.

## Baselines

The matched main comparisons include SC-DCTA, ENS–SharedPosterior,
probabilistic DCTA, hard-source DCTA, source-then DCTA, positive-only DCTA,
static risk, random replay, known-source DCTA, and full-information hindsight.
The repository also preserves transparent reconstructions of MemoRepair,
MemAudit, Graph Active Search, and ACIS-Risk.

Not every method is an official author implementation or a directly matched
terminal-recovery competitor. Read `docs/BASELINE_PROVENANCE.md` before using
the code or describing a comparison.

## Claim boundaries

- The 29-task MetaWorld test split is the locked transfer evaluation.
- The pooled 49-task result is descriptive because development and validation
  were observed during the broader research process.
- `ENS–SharedPosterior` isolates the acquisition policy while sharing DCTA's
  posterior; it is not an official reproduction of a native k-NN ENS system.
- MemoRepair and MemAudit are paper-based reconstructions, not author code.
- Known-source and full-information methods receive privileged information and
  are references, not deployable competitors.

## Citation and license

Citation metadata and the software license are intentionally pending author
approval. Do not publish this release candidate until both items in
`RELEASE_CHECKLIST.md` are resolved.
