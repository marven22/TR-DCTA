# Paper-facing results

This directory contains compact, versioned outputs that support numerical
claims in the LANTERN manuscript. It deliberately does not contain benchmark
datasets, model weights, simulator caches, or full episode ledgers.

## Statistical results

- `rq1_paired_bootstrap_95_v1.json` contains all paired 95%
  cluster-bootstrap results for the RQ1 theory-alignment comparison of LANTERN,
  cascade-aware continuation without rollout, and Immediate-Harm replay.
- `rq1_paired_bootstrap_95_v1.py` recomputes that report from the frozen
  MetaWorld and BabyAI outcome ledgers.

The report uses 10,000 draws. MetaWorld resamples held-out tasks. BabyAI
resamples held-out contexts. Each record contains the point estimate for
LANTERN minus its comparator, the 95% interval, number of clusters, and
cluster-level win, tie, and loss counts.

For RQ2 and RQ3, the repository retains the protocol and runner paths needed
to recompute direct and external-baseline comparisons. The manuscript reports
intervals only for comparisons that share a matched evaluation contract.

See [`../docs/STATISTICAL_PROTOCOL.md`](../docs/STATISTICAL_PROTOCOL.md) for
the exact inferential procedure and interpretation.
