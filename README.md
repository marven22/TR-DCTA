# LANTERN

Code and paper-facing results for **LANTERN: Safe Recovery from Corrupted
Robot Experience under Incomplete Provenance**.

LANTERN addresses post-incident recovery in agents that reuse persistent
experience. A harmful behavior may arise from an invalid source record and
from later records derived from it, even when the available provenance graph is
incomplete. LANTERN maintains a posterior over plausible harmful cascades,
uses finite-horizon rollout to choose a small number of diagnostic replays, and
then quarantines a capacity-constrained set of records before the agent resumes
operation. It does not rewrite or claim to repair archived memories.

The method was developed under the internal name **TR-DCTA**. Legacy filenames,
configuration identifiers, and artifact keys retain that name so frozen runs
and their hashes remain traceable. The public method and paper name are
LANTERN.

## What this repository contains

- LANTERN's posterior, rollout, and capacity-constrained quarantine code.
- Matched replay-selection baselines and transparent reconstructions of
  GraphAS, MemAudit, and MemoRepair.
- Frozen protocols, configurations, test suites, and independent verifiers for
  MetaWorld, BabyAI, and AgentDojo evaluations.
- Theory utilities and the paper-facing statistical outputs in
  [`paper_results/`](paper_results/), including the paired 95% cluster-bootstrap
  results used in the manuscript.

Benchmark datasets, MuJoCo assets, model checkpoints, simulator caches, and
large episode ledgers are intentionally excluded. See
[`docs/DATASETS.md`](docs/DATASETS.md) and
[`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

## Quick start

The deterministic tests do not require benchmark downloads.

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux or macOS
# source .venv/bin/activate

python -m pip install -r requirements/core.txt
python -m pip install -e .
python -m pytest -q
```

For a frozen benchmark evaluation, obtain the external ledger bundle, verify
its hashes, then run the associated runner and independent verifier. For
example:

```bash
python scripts/check_artifacts.py --group metaworld-full49
python scripts/run_metaworld_tr_dcta_full49_v1.py \\
  --config configs/metaworld_tr_dcta_full49_freeze_v1.json \\
  --output results/metaworld_tr_dcta_full49_v1.json --workers 8
python scripts/verify_metaworld_tr_dcta_full49_v1.py \\
  --config configs/metaworld_tr_dcta_full49_freeze_v1.json \\
  --report results/metaworld_tr_dcta_full49_v1.json \\
  --output results/metaworld_tr_dcta_full49_verified_v1.json
```

## Reproducing the paper statistics

The manuscript reports safe recovery as its primary endpoint. Paired 95%
cluster-bootstrap intervals use 10,000 draws and resample the appropriate
evaluation unit rather than individual dependent episodes. The released
statistical report identifies the population, cluster unit, compared methods,
point estimate, interval, and win/tie/loss counts for every RQ1 comparison.
The procedure and scope are documented in
[`docs/STATISTICAL_PROTOCOL.md`](docs/STATISTICAL_PROTOCOL.md).

## Repository map

```text
src/mcx/         LANTERN, posterior models, recovery adapters, and baselines
configs/         Frozen experiment contracts and seeds
scripts/         Construction, execution, aggregation, and verification tools
tests/           Deterministic unit and smoke tests
docs/            Protocols, theory, data setup, and reproducibility notes
paper_results/   Compact paper-facing statistics and result documentation
artifacts/       Hash manifest for external large artifacts
```

## Scope and comparison contracts

LANTERN, its ablations, and direct replay baselines receive the same archive,
provenance view, replay outcomes, replay budget, and terminal quarantine
contract. GraphAS, MemAudit, and MemoRepair are shown under their native
information and intervention contracts. Their results should therefore be
interpreted as contract-aware external comparisons, not as one uniform compute
budget ranking. Details are recorded with each protocol.

## Citation and license

Citation metadata, author list, and license selection remain pending author
approval. Please do not treat this repository as an archival release until a
tagged paper version and license are published.
