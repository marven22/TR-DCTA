# Release manifest

## Core contribution

- `src/mcx/terminal_recovery_dcta.py`: terminal-recovery acquisition and
  quarantine objective used by BabyAI.
- `src/mcx/metaworld_terminal_recovery_dcta.py`: domain-faithful MetaWorld
  terminal-recovery adapter.
- `src/mcx/prob_dcta_benchmark.py`: latent-source posterior and matched DCTA
  policy family.
- `src/mcx/publication_v2_posterior.py`: finite-particle importance-corrected
  posterior construction.
- `src/mcx/publication_v2_source.py`: source-estimation features and fitting.
- `src/mcx/sc_dcta_theory.py`: executable constructions used by the theory.

## External and controlled baselines

- `src/mcx/active_search_baselines.py`: ENS acquisition and Graph Active Search.
- `src/mcx/risk_aware_acis.py`: ACIS family and ACIS-Risk.
- `src/mcx/memorepair.py`: transparent MemoRepair paper reconstruction.
- `src/mcx/memaudit.py` and `memaudit_libero.py`: transparent MemAudit paper
  reconstruction and LIBERO adapter.
- `src/mcx/confidence_aware_dcta.py`: source-confidence adaptation.
- `src/mcx/prob_dcta_libero_baselines.py`: prior-aware matched baselines.

## Confirmatory/transfer runners

- Full MetaWorld: `run_metaworld_tr_dcta_full49_v1.py` and independent verifier.
- MetaWorld development bridge: `run_metaworld_tr_dcta_10task_bridge_v1.py` and
  independent verifier.
- BabyAI UnlockPickup: held-out runner and independent verifier.
- BabyAI OpenDoorColor: locked transfer runner and independent verifier.

## Supporting pipeline

The remaining included scripts reconstruct archive populations, masks,
posteriors, simulator recovery ledgers, baseline results, robustness analyses,
and secondary LIBERO comparisons. Historical medical/agricultural pilots,
downloaded papers, datasets, and raw laboratory outputs are excluded.

