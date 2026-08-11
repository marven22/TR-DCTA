# Meta-World DCTA experiment ledger

Generated: `2026-08-06T23:43:31Z`

## Reporting boundary

The definitive Meta-World method is **SC-DCTA**. Its confirmatory benchmark claim uses **29 untouched test tasks**, **87 primary archives**, **four replays**, **25% missing provenance**, and **weighted harmful-memory recall**. Results pooled across all 49 tasks are descriptive because development and validation tasks informed method construction.

Early Prob-DCTA, confidence-aware, oracle, and calibration studies remain preserved below, but they must not be substituted for the final corrected-ledger SC-DCTA evaluation.

## Publication-ready headline results

| Evidence | Frozen result | Intended use |
|---|---|---|
| Held-out method performance | SC-DCTA recall 0.6297; task-clustered 95% CI [0.5828, 0.6717] | Main paper |
| Held-out external comparison | SC-DCTA 0.6297 vs ACIS-Risk 0.5488; difference +0.0809 [0.0389, 0.1226] | Main paper |
| Held-out active-search comparison | SC-DCTA 0.6297 vs ENS 0.6198; difference +0.0099 [-0.0257, 0.0445] | Main paper; parity, not superiority |
| Held-out hard-source ablation | SC-DCTA 0.6297 vs hard-source 0.6335; difference -0.0038 [-0.0264, 0.0150] | Main paper; statistically tied |
| Behavioral recovery | Test task-macro recovery 26.90%, 51.03%, 82.11% at budgets 2, 4, 8 | Main paper |
| Post-localization remediation | Recovery conditional on localization was approximately 95% on held-out test | Main paper |
| Missing-provenance limitation | At budget four, SC-DCTA changed -3.15 pp [ -5.57, -1.12 ] from 0% to 50% missing provenance | Main limitation |
| Limitation mechanism | Loss concentrated in single-source ancestry (-9.02 pp) and small cascades (-9.95 pp) | Post-hoc diagnostic; appendix |
| Quarantine utility | Budget-four audit yield 85.7%; all 2,168 target-benign memories retained in deterministic benchmark | Main paper or appendix with stochasticity caveat |
| Archive scalability | At 200 memories SC-DCTA recall 0.5487 and recovery 0.4515; ENS 0.5935 and 0.4983 | Frozen post-hoc stress test; main scalability limitation |

## Final corrected-ledger baseline table

Four replays, 25% missing provenance, 29 untouched tasks, 87 archives. Privileged-information rows are references, not competitors.

| Method | Role | Weighted recall | Audit yield |
|---|---|---:|---:|
| Hard-source DCTA | Ablation | 0.6335 | 0.8736 |
| SC-DCTA | Proposed | 0.6297 | 0.8764 |
| Positive-only DCTA | Ablation | 0.6270 | 0.8649 |
| ENS | Active-search baseline | 0.6198 | 0.8678 |
| Floored Prob-DCTA | Ablation | 0.6149 | 0.8621 |
| Static-risk DCTA | Ablation | 0.6080 | 0.8534 |
| Source-then-DCTA | Sequential baseline | 0.5948 | 0.8132 |
| ACIS-Risk | External baseline | 0.5488 | 0.7816 |
| Source information gain | Sequential baseline | 0.2037 | 0.3017 |
| Random | Baseline | 0.1834 | 0.2989 |
| Known-source DCTA | Information oracle | 0.6560 | 0.8994 |
| Full-information hindsight | Ceiling | 0.7117 | 0.9454 |

## Complete study registry

### MW-00 — Meta-World feasibility and archive screen

- Phase: `exploratory`
- Paper role: `historical-only`
- Scope: Early archive-population screening before the publication-v2 pipeline was frozen.
- Primary condition: Screening, not a performance claim.
- Methods/references: Prob-DCTA candidate pipeline
- Headline: Retain only as provenance for benchmark construction; do not report as final performance.
- Evidence:

  - `configs/prob_dcta_metaworld_v2_screen.json` — SHA-256 `f540ed4ef1f396b2dd73ad3e69698fc2da6d83f7a7e91533383d421323a5d668`
  - `results/prob_dcta_metaworld_v2_screen.json` — SHA-256 `f183d205250bfb4433d8883f5172ca108dd3358a061fc07272a6d46b3ce05fda`
  - `scripts/run_prob_dcta_metaworld_v2_screen.py` — SHA-256 `b4389bd311e5232bc18382591168b310283da403c45a4e148d14c5ae1d27bdee`

### MW-01 — Frozen publication-v2 Prob-DCTA test

- Phase: `held-out-confirmatory`
- Paper role: `superseded-method-history`
- Scope: 29 Meta-World test tasks within a 41-task mixed LIBERO/Meta-World frozen test.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: Prob-DCTA, DCTA-Top1, ACIS-Risk, ENS, Source-then-DCTA, Known-source
- Headline: Meta-World recall: Prob-DCTA 0.457, ENS 0.486, Top1 0.254, ACIS-Risk 0.270, known-source 0.618. This motivated later Meta-World calibration and is not the final SC-DCTA result.
- Evidence:

  - `configs/prob_dcta_publication_v2_inference_final.json` — SHA-256 `14cdb70940f3ee7a8cf1ca7ac73b8f0fc151b26abce0c310078b3d6b7f235879`
  - `docs/PROB_DCTA_PUBLICATION_V2_TEST_RESULTS.md` — SHA-256 `eb45d6e795294864079f248a9ec221d4e293463f784923c62145d343a45e749b`
  - `results/prob_dcta_publication_v2_test_evaluation.json` — SHA-256 `ba481a6a9e191e69ea4595e520c2da986e571166429d830294341137d89ef6ab`
  - `results/prob_dcta_publication_v2_test_gate_analysis.json` — SHA-256 `75c0388ecbe9440809fd55c1759eebab91e6973ec89807a339ee130c66a19d49`
  - `scripts/analyze_prob_dcta_publication_v2_test.py` — SHA-256 `191858c2c3249bff80acfe190a35fb89970085830b74565ae56c1babf0829b28`

### MW-02 — Development oracle and planning diagnostic

- Phase: `development-diagnostic`
- Paper role: `appendix-mechanism`
- Scope: 10 development tasks; 90 archive conditions; no validation/test labels.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: Prob-DCTA, ENS, Random, Source-then-DCTA, exact posterior planner, information oracles
- Headline: Prob-DCTA 0.469 versus exact same-posterior planning 0.476 and hindsight ceiling 0.748; posterior localization, not planning depth, explained most of the gap.
- Evidence:

  - `docs/METAWORLD_DEVELOPMENT_ORACLE_DIAGNOSTIC_RESULTS.md` — SHA-256 `1c6ce5db4ebac6a3258c5d8dd62ff5384d10837e4939b0bae5ff69ca521cce10`
  - `results/prob_dcta_metaworld_development_oracle_diagnostic.json` — SHA-256 `8cfc5e1793a7e005f9f50edf6f85cccc2667bde768d58c9312bede9bbac1c3af`
  - `scripts/run_prob_dcta_metaworld_development_diagnostic.py` — SHA-256 `39bbee42af6639e24dfc68aedbaa2d03be32d481281b3532454388cc3c7b61ab`
  - `src/mcx/publication_v2_oracle.py` — SHA-256 `8a04b669230b33f8cbd9b6867f1ba55411c30919c49d0d76619ad30827ba25cf`
  - `tests/test_publication_v2_oracle.py` — SHA-256 `738512f8ef7783c5561f9deed8b5925e4c3ce3eb016fc75a8204e245c38cc9d7`

### MW-03 — Task-cross-fitted posterior calibration

- Phase: `development`
- Paper role: `appendix-method-development`
- Scope: 10 development tasks in leave-one-task-out folds; 30 primary task/rotation archives.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: adapted Prob-DCTA, external Prob-DCTA, ENS, Source-then-DCTA, known-source
- Headline: Adapted Prob-DCTA improved from 0.542 to 0.637 and reached 99.4% of the cross-fitted known-source score.
- Evidence:

  - `docs/METAWORLD_CROSSFIT_POSTERIOR_PROTOCOL.md` — SHA-256 `8de3d9f9e6ede8eac373c3cfbf97dea6bd33babd79eefabe287e91a4fb319444`
  - `docs/METAWORLD_CROSSFIT_POSTERIOR_RESULTS.md` — SHA-256 `32bbd9b0f14c28f4cde4c7585a87a08b4feb990873a68530b7646c8e9811ad04`
  - `results/prob_dcta_metaworld_development_crossfit.json` — SHA-256 `7a82de0bb7a0a6c0aba1460069cd4aa278ec5416782769d2b5e1b69b8f87db33`
  - `results/prob_dcta_metaworld_development_private_mask_consistent.json` — SHA-256 `4dd374be6334067cf812202a78a3afb94c1a781f770e5ca3833898f637dbc75b`
  - `results/prob_dcta_metaworld_development_public_mask_consistent.json` — SHA-256 `098462411fa36174fe88e27450bccc4023f74ec27856b80c74575f00d5a2abd8`
  - `scripts/run_prob_dcta_metaworld_crossfit.py` — SHA-256 `fd2cc70b2313414ef50c8128b9904c0d14d355332944ab01c24afbcc4a2ecf78`

### MW-04 — Frozen adapted validation

- Phase: `validation`
- Paper role: `appendix-method-selection`
- Scope: 10 validation tasks; 90 archive conditions; citation-consistent public ledger.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: adapted Prob-DCTA, adapted ENS, hard-source DCTA, known-source DCTA, external Prob-DCTA
- Headline: Adapted Prob-DCTA reached 0.646 versus ENS 0.670 and hard-source 0.685; the result motivated confidence-aware/hard-source investigation.
- Evidence:

  - `configs/prob_dcta_metaworld_adapted_cascade_validation.json` — SHA-256 `6b8d963d0f7f54ec8ca328a3d72c07553e839eef98190c97a1d9c85edf6dcceb`
  - `configs/prob_dcta_metaworld_adapted_source_validation.json` — SHA-256 `b917f0f5c9bed8650e7a54bb55d24681e37d24f51b0db0339b89dafeba696b12`
  - `configs/prob_dcta_metaworld_adapted_validation_freeze.json` — SHA-256 `4cdea77635e5a0a372330676c1261115021fd014997d1df6c0ad9c41c2187f66`
  - `docs/METAWORLD_ADAPTED_VALIDATION_RESULTS.md` — SHA-256 `300c4bf4f9e0669f2c758ebc46dcd5a6b4fa31b83b1d99a2afc648fea6bf68f9`
  - `results/prob_dcta_metaworld_adapted_validation_analysis.json` — SHA-256 `1b4c937f94f0856f93c00db808ffb6690911911117fe3637f0e287360d4752fc`
  - `results/prob_dcta_metaworld_adapted_validation_evaluation.json` — SHA-256 `caf65d55a713041113e2785962ac38c90c31e7513a4971b45cd37ad128775352`
  - `results/prob_dcta_metaworld_external_source_validation_evaluation.json` — SHA-256 `b7cf7a9b08e3144bf56f092d556a6eefc8d047a860c168491af716888cdb0e6b`
  - `results/prob_dcta_metaworld_validation_private_mask_consistent.json` — SHA-256 `9724d615fae70251a0ee3df33dae4eb3c634743a0eb4ea5fda405e196ebb060e`
  - `results/prob_dcta_metaworld_validation_public_mask_consistent.json` — SHA-256 `b2b4ae6ea3dab8e403803bd4cde57cb9354990f8047738b269b0d44c693db378`
  - `scripts/analyze_prob_dcta_metaworld_adapted_validation.py` — SHA-256 `3af072fd340a2876828fd76d35434327f07bd005a5c73994a5a3f6f919223cbf`

### MW-05 — Confidence-aware selector development test

- Phase: `development-negative`
- Paper role: `excluded-negative-development`
- Scope: Leave-one-task-out fitting on 10 Meta-World development tasks.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: confidence-aware DCTA, Prob-DCTA, hard-source DCTA, ENS
- Headline: The preregistered continuation gate failed; this selector was not promoted to the final method.
- Evidence:

  - `docs/CONFIDENCE_AWARE_DCTA_DEVELOPMENT_PROTOCOL.md` — SHA-256 `cae6aa2bf70cbdd994059effa1ee85e965b9b1a576c1f7a2cfdc08cd792e6914`
  - `docs/CONFIDENCE_AWARE_DCTA_DEVELOPMENT_RESULTS.md` — SHA-256 `ef1b234e264ef3b9422893cdd86094ec70e7786db8340972bd92cbe73920cd7d`
  - `results/confidence_aware_dcta_metaworld_development.json` — SHA-256 `d770a5a86e035d161e0efebef04fa3402be733c1b1500a66986c973e077173c8`
  - `scripts/run_confidence_aware_dcta_metaworld_development.py` — SHA-256 `3fa0edba3e8ea7678da40a2a9edc5246cfbfdcc30b9ee64af2bccfe61c50fdbe`
  - `src/mcx/confidence_aware_dcta.py` — SHA-256 `3692adb546adad544319be815f707ab1a545e0dd62c491f1905136511b03df1b`
  - `tests/test_confidence_aware_dcta.py` — SHA-256 `387140dfdfc10759dc8e9254974c26920c970e99ac714cf23e0622fe5ff9240c`

### MW-06 — Support-corrected DCTA development

- Phase: `development`
- Paper role: `appendix-method-development`
- Scope: 10 Meta-World development tasks; support correction and particle-quality checks.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: SC-DCTA, hard-source DCTA, known-source DCTA, SC-ENS, floored Prob-DCTA, Source-then-DCTA
- Headline: SC-DCTA reached 0.6497, improving over floored Prob-DCTA 0.6384 while matching hard- and known-source DCTA on development.
- Evidence:

  - `docs/SC_DCTA_DEVELOPMENT_PROTOCOL.md` — SHA-256 `8e4635dce3f731afe058f6d335d30cce0ca3a5f6d418141331992a6e8f280896`
  - `docs/SC_DCTA_DEVELOPMENT_RESULTS.md` — SHA-256 `7f52459994304d8568536641481ce2c2e352617ab606d6acda422c12c97852fe`
  - `results/sc_dcta_metaworld_development.json` — SHA-256 `6f6b4206977d5f60fe617d50879460eb906717da7a942f4156f1be36091e3a72`
  - `scripts/run_sc_dcta_metaworld_development.py` — SHA-256 `c35342eaa06249808ff9bfe35a243e90c6d1ef6a663f73121f775d52929dd6cb`

### MW-07 — SC-DCTA particle validation

- Phase: `validation-diagnostic`
- Paper role: `appendix-implementation-validation`
- Scope: Numerical validation of support-corrected particle approximation.
- Primary condition: Frozen SC-DCTA particle settings.
- Methods/references: SC-DCTA particle posterior, target posterior
- Headline: Implementation-quality validation; use to support fidelity of the approximation, not benchmark superiority.
- Evidence:

  - `docs/SC_DCTA_PARTICLE_VALIDATION_PROTOCOL.md` — SHA-256 `ea4f2d09d954079fda9f925372c3049ddc690cb5f0d538e8ee840359dacfb162`
  - `results/sc_dcta_particle_validation.json` — SHA-256 `f1ad8ded188b5b7e802fc373964956fd0b03b2b68ade96f1fc2d03bf36b671ef`
  - `scripts/validate_sc_dcta_particles.py` — SHA-256 `59b3fe7b54ea6cc4b48153b58c9d12cf01bec0c3a238f2c25b7e1059505b0f52`

### MW-08 — Frozen SC-DCTA held-out evaluation

- Phase: `held-out-confirmatory`
- Paper role: `main-paper`
- Scope: 29 untouched Meta-World tasks; 87 primary archives.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: SC-DCTA
- Headline: Weighted harmful-memory recall 0.6297 with task-clustered 95% CI [0.5828, 0.6717]; source Brier 0.0208.
- Evidence:

  - `configs/sc_dcta_metaworld_evaluation_freeze.json` — SHA-256 `205cebec291e370f7b4be48162da22124fb8179a29f6e09f37fd979a2c43fb3c`
  - `docs/SC_DCTA_METAWORLD_EVALUATION_PROTOCOL.md` — SHA-256 `1324623fc28a359affbe869095a6d2f3b8faa14ef943d762733a8b1e0820d61c`
  - `docs/SC_DCTA_METAWORLD_EVALUATION_RESULTS.md` — SHA-256 `232009624a9b9d234b85bd45d5a6cde18d77dd4d04f2d0f3a1ecec70d2b1db78`
  - `results/prob_dcta_metaworld_test_private_mask_consistent.json` — SHA-256 `a255b523ce0db947ebd3ea39f8f77af9260d5d55e30f3bffbf27d322e7962bbe`
  - `results/prob_dcta_metaworld_test_public_mask_consistent.json` — SHA-256 `ffed23cc04e2d239c5d477d18fed0826808921ed632ebe7cfd3b5baff5a4207c`
  - `results/sc_dcta_metaworld_evaluation.json` — SHA-256 `411728d5ed97e58c0d2eb83127dd58faa6d980f717156790a86da680a7123dc2`
  - `scripts/run_sc_dcta_metaworld_evaluation.py` — SHA-256 `3576afb161bcfd0e7c5ad4725a8619a883cea6a50e4775b451cd02389cde0953`

### MW-09 — Corrected-ledger held-out baseline comparison

- Phase: `held-out-confirmatory`
- Paper role: `main-paper`
- Scope: 29 untouched tasks; 261 archives; 12 methods; three budgets; three provenance masks.
- Primary condition: Four replays; 25% missing provenance.
- Methods/references: SC-DCTA, ENS, ACIS-Risk, Random, Source information gain, Source-then-DCTA, hard-source DCTA, floored Prob-DCTA, static-risk DCTA, positive-only DCTA, known-source DCTA, full-information hindsight
- Headline: SC-DCTA 0.6297; ENS 0.6198; ACIS-Risk 0.5488; hard-source 0.6335. SC-DCTA significantly beat ACIS-Risk and floored Prob-DCTA, and was statistically tied with ENS and hard-source DCTA.
- Evidence:

  - `configs/sc_dcta_metaworld_baseline_freeze.json` — SHA-256 `7c74992d1b6bf931f6712631e6137400b4f948edd92658edcfbea7d57af568d1`
  - `docs/SC_DCTA_METAWORLD_BASELINE_PROTOCOL.md` — SHA-256 `86b12ea7da23552bb104b00da0f60df12683f67c469a0ee42bd47aeee0751fa5`
  - `docs/SC_DCTA_METAWORLD_BASELINE_RESULTS.md` — SHA-256 `3ead3ac9aee7c66bf8bf373ce7624aa51ddea02376fc460108a850652961764d`
  - `results/sc_dcta_metaworld_baselines.json` — SHA-256 `e96ed6aeec986944850f7fac6cb11f51178f7e575acdf9317d15b6ab4f7d4a60`
  - `scripts/run_sc_dcta_metaworld_baselines.py` — SHA-256 `7e6bdf0d6afdbb233e4e34d88d603ffe9489315fff57af0bb4c0e2a000dda645`

### MW-10 — Recovery mechanism development study

- Phase: `development-diagnostic`
- Paper role: `appendix-behavioral-design`
- Scope: 10 development tasks; transition from detection to quarantine-and-fallback recovery.
- Primary condition: Forced harmful-descendant retrieval followed by budgeted audit.
- Methods/references: SC-DCTA, ENS, hard-source DCTA, floored Prob-DCTA, Source-then-DCTA, oracle
- Headline: Established that recovery is mostly limited by localization and that quarantine succeeds in roughly 92-95% of localized development episodes.
- Evidence:

  - `docs/SC_DCTA_METAWORLD_FORCED_EXPOSURE_DEVELOPMENT_RESULTS.md` — SHA-256 `efdb7ef25094e3488d2ff264cabeb4635d97a66e62285fb2aef2c6032d80d9fe`
  - `docs/SC_DCTA_METAWORLD_RECOVERY_DEVELOPMENT_RESULTS.md` — SHA-256 `2cf7cc20484b88c41fb9f6f0785cc6fb4037fd75960bf8cf2d7441a9c4e0e81a`
  - `docs/SC_DCTA_METAWORLD_RECOVERY_PROTOCOL.md` — SHA-256 `470d530f30f324f237ad3d91a87d17eb1faafe0e1a02e6213b4a39eb8cc4020f`
  - `results/metaworld_forced_exposure_development_b2_evaluation.json` — SHA-256 `412420c2a7fd5a4fada15cf42d526a72fbd52c6cfb7343049439e98a3939ffdc`
  - `results/metaworld_forced_exposure_development_b8_evaluation.json` — SHA-256 `1b97e8697077518ed5d9d61211aa554fb5f7b8515085833422633948329e8296`
  - `results/metaworld_forced_exposure_development_evaluation.json` — SHA-256 `c77420c3b5b8d9d38c7a4a50a78e65651faeaa1cb48061dc4037fa512ff65ed5`
  - `results/metaworld_forced_exposure_development_m0_b2_evaluation.json` — SHA-256 `0b301c9afb030a5b4004db580bf8f57da574a3fa4d23c29d10c28adbf7b13d73`
  - `results/metaworld_forced_exposure_development_m0_b4_evaluation.json` — SHA-256 `c8121dee64156a97fee9295acb902077316df29985b99be1a73908f95f4c1dff`
  - `results/metaworld_forced_exposure_development_m0_b8_evaluation.json` — SHA-256 `1ff9be1fe95d8c6faf502029764549e564459399df9e52556af81544c4520d73`
  - `results/metaworld_forced_exposure_development_m50_b2_evaluation.json` — SHA-256 `5960a7696de4c504417d4a9b00f8351fe1121ff7988c36a57737400cf66797f7`
  - `results/metaworld_forced_exposure_development_m50_b4_evaluation.json` — SHA-256 `d1ef0548b1dd001479b99b3db25e4a4b1ab4ffda84eb77cda00caf3eb8422228`
  - `results/metaworld_forced_exposure_development_m50_b8_evaluation.json` — SHA-256 `4be5fc081bb4e949b727d909f88a471a288bfcf550554abf833d5f021a734bb6`
  - `results/metaworld_recovery_development_b2_observable.json` — SHA-256 `7119bff02935b254754693bc04c8f45f4103a0b5f3056e09ecaac660620dcc53`
  - `results/metaworld_recovery_development_b2_private.json` — SHA-256 `08111b675e28b787413b4cb95d6d1d02e6b03ed5006423572861eb2c7075981d`
  - `results/metaworld_recovery_development_b8_observable.json` — SHA-256 `8d0c1b416693841fe46bb1a014c9be9fc4613f48d28f69839cff3143b862046f`
  - `results/metaworld_recovery_development_b8_private.json` — SHA-256 `2fce1412b853d7f0588ed39489aaa0f90c74809e46b8e57f6b187d50ff9e09f7`
  - `results/metaworld_recovery_development_evaluation.json` — SHA-256 `e633829e24324b1b329dc80354e7fba2202b0bd9849692bcdeba4a06bc3224aa`
  - `results/metaworld_recovery_development_events.json` — SHA-256 `cb2910aff80093b3c0b728f82c766c77f4b5e7457a6facf7eadf013b2267abdd`
  - `results/metaworld_recovery_development_m0_b2_observable.json` — SHA-256 `d63fc5c4014a011c46da0def2cb086c1255715f0a4eaf412b0eed8ff2a2db524`
  - `results/metaworld_recovery_development_m0_b2_private.json` — SHA-256 `09fcfeeea3fbe42ed28564d4733fc2c50df2e9787f693c77ab0cb889fe4a2b3a`
  - `results/metaworld_recovery_development_m0_b4_observable.json` — SHA-256 `ac6ba087dc3f422961c7735eb3a696dcf7bb1ce15b228840d608f28240d936d3`
  - `results/metaworld_recovery_development_m0_b4_private.json` — SHA-256 `912f2377c373977e95837fc7ceb37c33433fad72fbc65d99c682962b3e9baedd`
  - `results/metaworld_recovery_development_m0_b8_observable.json` — SHA-256 `d79dd1c04f8c999c616df79cb176fa508308d7c6e87f3fb3be15db9878edaaf7`
  - `results/metaworld_recovery_development_m0_b8_private.json` — SHA-256 `c2d9a1200a13601c35eb0667349c1eb7e4cd47a54533b95bcd0c52178ca7f586`
  - `results/metaworld_recovery_development_m50_b2_observable.json` — SHA-256 `1b3dd20d2d8ec890021be06875d916c77dc194a687b0db953f48e75f16f0ceca`
  - `results/metaworld_recovery_development_m50_b2_private.json` — SHA-256 `66c83835fa8b2340c58ad16ee28c7cb57210929ae3238a52d4977140b5879e57`
  - `results/metaworld_recovery_development_m50_b4_observable.json` — SHA-256 `cbf06d3db7c01f4575fac3fdba46945322b577648cfab94fe29a3fff6ba929a2`
  - `results/metaworld_recovery_development_m50_b4_private.json` — SHA-256 `26abf5bbb24d02fa13fd9feab09c5c108636d26efba792002ee197148c1558df`
  - `results/metaworld_recovery_development_m50_b8_observable.json` — SHA-256 `73177e38c64dbcc55a4c153e3798a5aca1fd62749ff480c3744588d7c4c43ce5`
  - `results/metaworld_recovery_development_m50_b8_private.json` — SHA-256 `22eb359b92c4bfe86a1f08dd6ba6a9f0bf57e2867bb5dad75e049cf61cc56e6a`
  - `results/metaworld_recovery_development_observable.json` — SHA-256 `4d787bafd27af6979d6daf8077cbfa7bbd829649ba2f0c9d8e5530b4dc553eaf`
  - `results/metaworld_recovery_development_private.json` — SHA-256 `453146815054ef5dd859f2ecd089c8d2661e37dcadd01fa1ef80036be0a28caf`
  - `results/metaworld_recovery_development_smoke_events.json` — SHA-256 `3cd22a73fbb9aa84ab92c05f944d657afa43fba63bd4b4ced3717eab0e5380df`
  - `scripts/evaluate_metaworld_recovery.py` — SHA-256 `abcd9dd268a98618a85726ad5901c5493c3cea0d440441982975b75fc52b0665`
  - `scripts/run_metaworld_recovery_events.py` — SHA-256 `6cb1ffa965c0f81ce6f0b14da6128e2b549a6b0dbc43fee1f1db11853e7cafb5`

### MW-11 — Frozen 49-task forced-exposure recovery study

- Phase: `held-out-confirmatory-plus-descriptive`
- Paper role: `main-paper`
- Scope: 919 harmful-descendant episodes: 182 development, 172 validation, 565 untouched test.
- Primary condition: Budgets 2, 4, and 8; exposed harmful descendant forced to retrieval rank one.
- Methods/references: SC-DCTA, ENS-SharedPosterior, hard-source DCTA, known-source DCTA, full-information oracle
- Headline: Untouched-test SC-DCTA task-macro recovery was 26.90%, 51.03%, and 82.11% at budgets 2, 4, and 8; recovery conditional on localization stayed near 95%. SC-DCTA and ENS-SharedPosterior were tied.
- Evidence:

  - `configs/metaworld_forced_exposure_freeze_v1.json` — SHA-256 `f9afdf6794983462edf15318e11dc064a1f360f38b2a0ce7bce03c06b8e95af9`
  - `docs/SC_DCTA_METAWORLD_FORCED_EXPOSURE_ALL49_RESULTS.md` — SHA-256 `ff1dd5a7f46e70d313728e7e30099f51bf47dce76cf20ff12e323e6aeb74f4dd`
  - `results/metaworld_forced_exposure_all49_aggregate.json` — SHA-256 `1e38a8de14fb006a1f57d73f513ca7754227c348a167512cb616b95eba0262b6`
  - `results/metaworld_forced_exposure_test_b2_evaluation.json` — SHA-256 `3058510c881b6286273b7fb5d8ffb81abf9977dd7a4f4c2a9ad77898c88533d3`
  - `results/metaworld_forced_exposure_test_b4_evaluation.json` — SHA-256 `55994482207b18cfff4506b9d8471b650ceb978a2f8301dac2db9931e87afc37`
  - `results/metaworld_forced_exposure_test_b8_evaluation.json` — SHA-256 `9a93ccadefa55a1603f6f69fe0ee573adab5706b7938e70bb4b7bdef364b847b`
  - `results/metaworld_forced_exposure_test_m0_b2_evaluation.json` — SHA-256 `d28d094a06688789154b90943a8e436d828791c3df7838f6cd6d5c8a8f181e6a`
  - `results/metaworld_forced_exposure_test_m0_b4_evaluation.json` — SHA-256 `fac4632f2558d97d7213de1326f8993aedeeb58d304f1fc8a6a035f8268fb13c`
  - `results/metaworld_forced_exposure_test_m0_b8_evaluation.json` — SHA-256 `928f37dce24a9228fec571c4d4b3c441451b1ce2d932c38a4e8cedcc654d14f1`
  - `results/metaworld_forced_exposure_test_m50_b2_evaluation.json` — SHA-256 `fcbfd16e1470045bccc0f1ba7ab48983fd976361d2690a8cce1462acc62d5a44`
  - `results/metaworld_forced_exposure_test_m50_b4_evaluation.json` — SHA-256 `4f7faeb05ef6c8ce12cebeabd0739b237be2e6a7371f413e0dee75bf05915665`
  - `results/metaworld_forced_exposure_test_m50_b8_evaluation.json` — SHA-256 `7f8745fb1c92b55547b26be7536c27418a2396affb41493a9c932dffa2050c1f`
  - `results/metaworld_forced_exposure_validation_b2_evaluation.json` — SHA-256 `fa7f8c8393a2ede0b3bd6aff43769f3c7adc27e376ff5dd47bac75a6fa669308`
  - `results/metaworld_forced_exposure_validation_b4_evaluation.json` — SHA-256 `d2d25ebc0c0ff3c6369524296a1cbc981cb2c149b5c7c2a134b797e662cc7051`
  - `results/metaworld_forced_exposure_validation_b8_evaluation.json` — SHA-256 `236547965125eb85ca121e27cb36f0312c28cd8ce4188a441b851e6216e405a5`
  - `results/metaworld_forced_exposure_validation_m0_b2_evaluation.json` — SHA-256 `e33f2636898d38b6c6214a7a071416fbb1545bca0bc38062fd0e8d3871647029`
  - `results/metaworld_forced_exposure_validation_m0_b4_evaluation.json` — SHA-256 `a70f188f9856b7093b2d6f72a90a7a8a3900899fd53995cbf35bb3dbb497e4d5`
  - `results/metaworld_forced_exposure_validation_m0_b8_evaluation.json` — SHA-256 `b56a0534853eb3e1a187d3226673b9ac82f509dedd0a2977a575ca5ee474b54f`
  - `results/metaworld_forced_exposure_validation_m50_b2_evaluation.json` — SHA-256 `e6413b0b5768be96fe64c7105759d5df872a978fe53b29d0e64e6d13091948ab`
  - `results/metaworld_forced_exposure_validation_m50_b4_evaluation.json` — SHA-256 `28a32b97dead0a50eb724aad80a133e388822ce17350985d8bb713aaa6ab3b45`
  - `results/metaworld_forced_exposure_validation_m50_b8_evaluation.json` — SHA-256 `52bb4fd7715336a9d030c86e27d25473e50197a0e5dc74cbb68d6ab397c1243c`
  - `results/metaworld_recovery_test_b2_observable.json` — SHA-256 `4c3d605f0ed2129d0bce0a9b4e210a6572a7043306b28770e60dc55e9cb112fd`
  - `results/metaworld_recovery_test_b2_private.json` — SHA-256 `ad41de01b137999a59d59be916c93c6a8bfcabd198f8895cc104e3de5fdef532`
  - `results/metaworld_recovery_test_b4_observable.json` — SHA-256 `898877b975200af474e3fc95404eb0f4906ef2601098accacfd8acf940114a8b`
  - `results/metaworld_recovery_test_b4_private.json` — SHA-256 `2bde7854300ca22cce4fa3556ea577c6b2271504646a579c98e9ce155731d06b`
  - `results/metaworld_recovery_test_b8_observable.json` — SHA-256 `d46dc0a1c67750afbecd7dfdac6ffbc51f50b4a5bf10763977d8f0e95cc8dc9d`
  - `results/metaworld_recovery_test_b8_private.json` — SHA-256 `1511cda23664640b313b287b4fb9843cd3fc1e42eb799da904f6304c662bcf91`
  - `results/metaworld_recovery_test_m0_b2_observable.json` — SHA-256 `5785aafe1b336338fcc0e525ecc02aabac88802d5d3093cff510c271d0db96fd`
  - `results/metaworld_recovery_test_m0_b2_private.json` — SHA-256 `ac5c4fcc357ffdce266484b4f95e14be795e8083ba35c163cbb4a925a702a94a`
  - `results/metaworld_recovery_test_m0_b4_observable.json` — SHA-256 `4397a23d84e16260db9383170872968f6c5fc0dfd9ca9820fe131f5213fd473b`
  - `results/metaworld_recovery_test_m0_b4_private.json` — SHA-256 `93341813ea0488fd3c33e11a4b239824f1c75f68a5fc12a25a1634d3034a0c61`
  - `results/metaworld_recovery_test_m0_b8_observable.json` — SHA-256 `fa90107b1952326f28558d7edc3a1612c7b372b30cdbc2838ad3eedc188f0b6a`
  - `results/metaworld_recovery_test_m0_b8_private.json` — SHA-256 `b6b1cfe74df18dabed60e87815a6247e1dd67807087058c53410b030eda00b9b`
  - `results/metaworld_recovery_test_m50_b2_observable.json` — SHA-256 `5b87114af228cd7fc5a718eae5b06243d8ba947775bcc6625857a24601e58346`
  - `results/metaworld_recovery_test_m50_b2_private.json` — SHA-256 `a8a8f344b885f8e3857e92a8f485672e066d77797dcefc548a06d822d8080a2a`
  - `results/metaworld_recovery_test_m50_b4_observable.json` — SHA-256 `bfcb056dd412bb0a14afd424123ac8ef72e52b658ec0d25ba3a7f078d6ae899b`
  - `results/metaworld_recovery_test_m50_b4_private.json` — SHA-256 `f27e3ced57a32a526fad5e90edc7e2b80baebacdf0192e706c6066c62909d05e`
  - `results/metaworld_recovery_test_m50_b8_observable.json` — SHA-256 `c879505ea6b90010760305ea93d56c372c1445185c90fbc82058ad209ca92467`
  - `results/metaworld_recovery_test_m50_b8_private.json` — SHA-256 `0b76e5b8a41b29c93b91c137d71f84b4fee4e9ef3039a1dc078f15dccfddffce`
  - `results/metaworld_recovery_validation_b2_observable.json` — SHA-256 `72bd99651a316964307ff5bee94b3ef0d72bb8463934c7bcd7741084b842ddb4`
  - `results/metaworld_recovery_validation_b2_private.json` — SHA-256 `29858c5c997bf90565679ce3f1627dc0754c59167da36912d5c1ab3f4d32e0d5`
  - `results/metaworld_recovery_validation_b4_observable.json` — SHA-256 `fedca7f51c911d5c8fa46b4992164cec96b8fc371df50b426d624c98411ad68f`
  - `results/metaworld_recovery_validation_b4_private.json` — SHA-256 `ec1ec94615c708494478fb8aeaaa46f4c389bdf0744ff9cb27fe46e0cc16a223`
  - `results/metaworld_recovery_validation_b8_observable.json` — SHA-256 `c5728b8e150f6151830f93e3327dfbd8cd703d761e91520b3976bc768b5f81df`
  - `results/metaworld_recovery_validation_b8_private.json` — SHA-256 `12564fe552a788e791c4f4c0dee8dccfb6c1163d06e7e26a1d56d1f4da8463fe`
  - `results/metaworld_recovery_validation_m0_b2_observable.json` — SHA-256 `ff9ebbb39145a1212fb414c413e348c6e76ff772d2656ea7ce4c29a3d341d750`
  - `results/metaworld_recovery_validation_m0_b2_private.json` — SHA-256 `e8fdbe5fe734dca0e2dc6d5d7ec227714254cdf86c7690929f321c66a824e97d`
  - `results/metaworld_recovery_validation_m0_b4_observable.json` — SHA-256 `f9bcc423a051b83719d04b104b584f271883118c39a938b5925bb9c25ff36095`
  - `results/metaworld_recovery_validation_m0_b4_private.json` — SHA-256 `86aa70e0c83612536b1657c3e13a6860c867919a302ce80051498564e4b3ab60`
  - `results/metaworld_recovery_validation_m0_b8_observable.json` — SHA-256 `3a6cc6727f750d35728895db46b60814287c3cef8b7827ea77b05b1c855c1819`
  - `results/metaworld_recovery_validation_m0_b8_private.json` — SHA-256 `2c679a6bfb1a750848773222959c45006de5a5c6f09d9c2e0b17722740854919`
  - `results/metaworld_recovery_validation_m50_b2_observable.json` — SHA-256 `bb6e887c14e590701ce8a90659ad5147c5987f1cbd944282916fb9319ce60bd4`
  - `results/metaworld_recovery_validation_m50_b2_private.json` — SHA-256 `2f1f0b0c47d487988c43273fc40751e3a4083ab68bd5e3619678ece70603c4e5`
  - `results/metaworld_recovery_validation_m50_b4_observable.json` — SHA-256 `02ca9ec0e18f793328dd9eb45982239f231dd009078f7af41c0d26ccc2f06b06`
  - `results/metaworld_recovery_validation_m50_b4_private.json` — SHA-256 `479f6695327a8bbc34efc5289f4e952cee6654313003bb2b1b983f75e96e1baf`
  - `results/metaworld_recovery_validation_m50_b8_observable.json` — SHA-256 `5475adabe8bc4ed6cf081d973f2badfd4bd55003c5f03ba22d0e78e65ef33c92`
  - `results/metaworld_recovery_validation_m50_b8_private.json` — SHA-256 `722dc408a3c8a567eff1712332824e4862d38120b7313da4ad6e03a13ba699fb`
  - `results/sc_dcta_metaworld_validation_crossfit.json` — SHA-256 `1d17ff91bcdb6cc76129135c9c1ad2d776cc4983f7d81164e4677947592d588a`
  - `scripts/aggregate_metaworld_forced_exposure.py` — SHA-256 `fa312b866bdba57ddc2b8533866841ba9e57f973b8edb7b49b13fb15c2f4d5e5`
  - `scripts/evaluate_metaworld_forced_exposure.py` — SHA-256 `36dfdb5237b64ce8facff788e3227e4e1ffc5008b5a989cbb92551b38d2e089f`

### MW-12 — Task-scoped quarantine utility and audit-cost study

- Phase: `confirmatory-reanalysis`
- Paper role: `main-paper-or-appendix`
- Scope: 49 tasks; 147 primary archives; 3,087 candidate-memory instances.
- Primary condition: 25% missing provenance; budgets 2, 4, and 8.
- Methods/references: SC-DCTA, ENS-SharedPosterior, hard-source DCTA, Source-then-DCTA, floored Prob-DCTA, known-source DCTA, oracle
- Headline: At budget four SC-DCTA made 504 harmful and 84 benign replay calls (85.7% audit yield), retained all 2,168 target-benign memories, and avoided cross-context deletion by task-scoped quarantine.
- Evidence:

  - `docs/SC_DCTA_METAWORLD_QUARANTINE_UTILITY_PROTOCOL.md` — SHA-256 `1ddfb48af14ad080a800955d2ed4f46b40017b6ee83defba07639218fc70cd6b`
  - `docs/SC_DCTA_METAWORLD_QUARANTINE_UTILITY_RESULTS.md` — SHA-256 `6949b0181f2c967681038c8920a7013cb2edff4f9a1d5eabeb41e6360e957565`
  - `results/metaworld_quarantine_utility_all49.json` — SHA-256 `277855c16ab6f2e1444d5447732080186bbdf9b8216b8cec99cda5247f1a0264`
  - `scripts/analyze_metaworld_quarantine_utility.py` — SHA-256 `6227ed7c454bc16dc957d5ad53dea7da46b3a305d013d2c6a845f728f4f0ed28`

### MW-13 — Missing-provenance recovery robustness

- Phase: `held-out-confirmatory`
- Paper role: `main-paper-limitation`
- Scope: All 49 tasks across 27 split/mask/budget cells; primary inference on 565 untouched-test episodes.
- Primary condition: Four replays; compare 0% with 50% missing provenance.
- Methods/references: SC-DCTA, ENS-SharedPosterior, hard-source DCTA
- Headline: On held-out test, SC-DCTA recovery declined 3.15 points [1.12, 5.57] from complete to 50%-missing provenance; ENS was more robust by 3.09 points at budget four.
- Evidence:

  - `configs/metaworld_provenance_recovery_freeze_v1.json` — SHA-256 `7d55ac5bdcf822790567a8c34166860d3f5974264b19160c8b8ec579f8e000e0`
  - `docs/SC_DCTA_METAWORLD_PROVENANCE_RECOVERY_PROTOCOL.md` — SHA-256 `315e3507f19bfca204a0d659f19075717d56458a3e057037c1f2f9dcd5229db2`
  - `docs/SC_DCTA_METAWORLD_PROVENANCE_RECOVERY_RESULTS.md` — SHA-256 `efba3093e7520c6d7b6bdc2d360409f5f3be51efce7fb98564d8eefdf2d715d7`
  - `results/metaworld_provenance_recovery_all_masks.json` — SHA-256 `570557f62d1eae27e9c448395764ba372098979b40572667fe8c7123ec1984ef`
  - `scripts/aggregate_metaworld_provenance_recovery.py` — SHA-256 `aa6d44b3851b6e797bd4c618796bceb36ad74ff23acbc87968572f8546327b85`

### MW-14 — Missing-provenance failure-strata diagnostic

- Phase: `post-hoc-held-out-diagnostic`
- Paper role: `appendix-limitation-mechanism`
- Scope: 565 paired held-out harmful-descendant episodes at complete and 50%-missing provenance.
- Primary condition: Four replays; no method modification or rerun.
- Methods/references: SC-DCTA, ENS-SharedPosterior
- Headline: Loss concentrated in single-source ancestry (-9.02 points) and small cascades (-9.95 points), not deep descendants; the limitation is best described as insufficient lineage-evidence redundancy.
- Evidence:

  - `docs/SC_DCTA_METAWORLD_FAILURE_STRATA_PROTOCOL.md` — SHA-256 `ad3d5c5ba49c88055606c365a4c7c3f34daada640d038fe818025ebca37be5ab`
  - `docs/SC_DCTA_METAWORLD_FAILURE_STRATA_RESULTS.md` — SHA-256 `1a4826e6fa9b00629b7f64c66bd4036bc3a691f0244556d2f507e4a8bf1b4c17`
  - `results/metaworld_failure_strata.json` — SHA-256 `a2b66432730029ae85d8e812832f59a4a2bc855dbd443e8b4dc291fe4e76b44c`
  - `scripts/analyze_metaworld_failure_strata.py` — SHA-256 `d1bc2b4c7cba0f4b09cd27f86e67e474d9f22bb5fbb6489752edd253d8e51d9b`

### MW-15 — Frozen task-matched archive-scalability stress test

- Phase: `frozen-post-hoc-stress-test`
- Paper role: `main-paper-scalability-and-limitation`
- Scope: 49 Meta-World tasks; nested 21/50/100/200-memory archives; 31,752 audit rows and 66,168 behavioral-recovery rows.
- Primary condition: Four replays; 25% missing provenance; 29-task evaluation panel is disjoint from fit but previously inspected.
- Methods/references: SC-DCTA, ENS, hard-source DCTA, ACIS-Risk, floored Prob-DCTA, deterministic random
- Headline: At 200 memories SC-DCTA retained 0.5487 recall and 0.4515 recovery, but trailed ENS by 0.0449 recall and 0.0468 recovery; acquisition time scaled 275.9x from 21 to 200 memories under shared load.
- Evidence:

  - `configs/metaworld_scalability_freeze_v1.json` — SHA-256 `e0c4dca562b142fd2edf8b86381c87d02bd00cc8070dd2521b0ec7f6b711c35a`
  - `docs/SC_DCTA_METAWORLD_SCALABILITY_PROTOCOL.md` — SHA-256 `0ef0cdc3e27d8019313b341dda7641cdbf495aadf93456c574946ca1a30e224c`
  - `docs/SC_DCTA_METAWORLD_SCALABILITY_RESULTS.md` — SHA-256 `052910bd4ca3c32bfdf3135cb17e5c26c2f8097b8cb976591e6c1ea75d3edec1`
  - `results/metaworld_scalability_analysis.json` — SHA-256 `aa9f991f9882440c2b94f5acd55357d99a4536018657f4edbfff3044a46d00e5`
  - `results/metaworld_scalability_development.json` — SHA-256 `fea997d4c299e77706368e2b37b4ef613eecad6bc3d9ef357996c17cc9b7c334`
  - `results/metaworld_scalability_development_shard0.json` — SHA-256 `86bdd45047bff91ce6839426ec32273f6d37ee6f0289dfbdbc202868610b2222`
  - `results/metaworld_scalability_development_shard1.json` — SHA-256 `6d1b78019d6fb406143204849e4d59f3b7f3bf7559fb5279c8c5e6afd712405f`
  - `results/metaworld_scalability_development_shard2.json` — SHA-256 `c5e9289bff4639368ce85275c71ec2da92736904eed3a06794f4bb067f42f636`
  - `results/metaworld_scalability_development_shard3.json` — SHA-256 `07d196f45fee2cc7b2c2475585879c5fa8c4f281ba80e9d59022e77b0fa845a7`
  - `results/metaworld_scalability_development_shard4.json` — SHA-256 `8b154670f2c10d567a6d7d2fd97deaa4fa38dfe2d3b055dbfe71948277946c8d`
  - `results/metaworld_scalability_development_shard5.json` — SHA-256 `01468c2164d06dbf22b5ac13458631e047c9a703af4c07d34914010cc8e0215f`
  - `results/metaworld_scalability_development_shard6.json` — SHA-256 `6819a3f6993f09157090f1abf6a8ec86e181c762df635ee8b4c6f103b9070bed`
  - `results/metaworld_scalability_development_shard7.json` — SHA-256 `10c5fb254fb74903cee8b07b70c73c2df8b1fc357679de18c52c58c2f370502f`
  - `results/metaworld_scalability_fullparticle_smoke.json` — SHA-256 `39cf808201c3132c1629eb9b55661e973319874c30aabf1aeaf03feb41b93dd2`
  - `results/metaworld_scalability_memory_profile.json` — SHA-256 `94706f1fc71b252c232a4ac4f20ac4e909bfd01e7f99c8b7425434736cd7184f`
  - `results/metaworld_scalability_recovery_development.json` — SHA-256 `31fc26ca18130f2ba21c119138440e513f9ef1d75479990e47e70d0ff4668fbc`
  - `results/metaworld_scalability_recovery_test.json` — SHA-256 `85a06ee463313df258101fac7eb2c372cc6f29c90c26e22f20cfa110e4b38179`
  - `results/metaworld_scalability_recovery_validation.json` — SHA-256 `e85aee2f81aed4833334482b8caa97612119218952cb0140f7e0a4adaf1a4745`
  - `results/metaworld_scalability_smoke.json` — SHA-256 `cfaad81057e12a9c3da15a5585280d4f0183781e09ebbfa002bf0b46d0cce80b`
  - `results/metaworld_scalability_test.json` — SHA-256 `fcf1a17ca4c0651b9b7da711623b13bda1d276f65b7454f2586739d969aa4094`
  - `results/metaworld_scalability_test_shard0.json` — SHA-256 `2bf0f092305736e46675700ec84aae5069188700c5d20d204741afcf3ae5f77e`
  - `results/metaworld_scalability_test_shard1.json` — SHA-256 `891804cc5ec63bce0383331112893c4d31f01ca6170b3ab017cd40dbe54936bc`
  - `results/metaworld_scalability_test_shard10.json` — SHA-256 `4aa2b965de73be500f27ce3527f1e381399a312b4beae22b3029e497f672938f`
  - `results/metaworld_scalability_test_shard11.json` — SHA-256 `2470863b993e9bda84a50ac6e152121e8e8c4d23ce875fe4dae109ef9f781495`
  - `results/metaworld_scalability_test_shard2.json` — SHA-256 `6c69eab7f01ddd84e1351798c7406a08ca7fc50e2b655c49c386db116e48a642`
  - `results/metaworld_scalability_test_shard3.json` — SHA-256 `8decfa9f0c4938b62c13090deac673664623fdc752fcf968005e13118346c108`
  - `results/metaworld_scalability_test_shard4.json` — SHA-256 `1322e2e0155daf1b594ea664981c2eb06d05fa5534870a3d88571825a7b57903`
  - `results/metaworld_scalability_test_shard5.json` — SHA-256 `a41067844e530883240ade53a02a0407beb44274c857f1cbc0fb6548455cade9`
  - `results/metaworld_scalability_test_shard6.json` — SHA-256 `1419a7237b51a3729134d032eb69f56ecf6c83ce63213451af9c6684263de43c`
  - `results/metaworld_scalability_test_shard7.json` — SHA-256 `e5f63cc53a1ef938614f9286410ed1dbed1d2080bf538fad849f5aa5aa1ef794`
  - `results/metaworld_scalability_test_shard8.json` — SHA-256 `c2699ab32e423655859dccf6653ca3441fe5c0369f32716e95f20791e7adceba`
  - `results/metaworld_scalability_test_shard9.json` — SHA-256 `1c3b7163ac6d591c894aeadf7fdb029512c9c82fa4cbdac6361986dbeb36f7dc`
  - `results/metaworld_scalability_validation.json` — SHA-256 `992ec612fba242caace5e216e2dff7c6f6c6094d4cfc132742f029f772c63f16`
  - `results/metaworld_scalability_validation_shard0.json` — SHA-256 `0f6f8a8c4db3ff80666f0abf83897cee5e49e88c1ae910f4deebd996bf47fb2e`
  - `results/metaworld_scalability_validation_shard1.json` — SHA-256 `85c23d47e2700ecc5ff068d9e9bf6fb1a686fe84444e0c4d0e962e30c0a68069`
  - `results/metaworld_scalability_validation_shard2.json` — SHA-256 `b9e2b0deeaf9301a337611c66f917340bfa28442706d46eb1fca9005888aa26c`
  - `results/metaworld_scalability_validation_shard3.json` — SHA-256 `11d63817c07ad801779829cec7d439b03f2e66d6f6ac18e123f82513599c6754`
  - `results/metaworld_scalability_verification.json` — SHA-256 `00484bd6b72ff61ccd9da515a0d711c10198663a8375fd0e0c8c998366060b11`
  - `scripts/aggregate_metaworld_scalability.py` — SHA-256 `2ccad580b87e9ab4a0246d506a3cc85f52b09d0a1530594b709be0b54b3e0c62`
  - `scripts/analyze_metaworld_scalability.py` — SHA-256 `d40aba04eeee710731886fe8955fe060917284023b96fd55941d02672e099565`
  - `scripts/evaluate_metaworld_scalability_recovery.py` — SHA-256 `232436eb9c2a32e345f27b1c9d6de2a624aaf80c523fdedc7d853fd1f218685e`
  - `scripts/run_metaworld_scalability.py` — SHA-256 `0e1ab84cfc3d70600bd28a7ba9c765061919addaed965783d3f5712fef6906d8`
  - `scripts/verify_metaworld_scalability.py` — SHA-256 `ea0d327227ba51222b89be9f3fbe6c83624eed3ae3703635527e773683991306`
  - `src/mcx/metaworld_scalability.py` — SHA-256 `e3fc5157ef5284f51777a643dcbd49294d0bbf1e903f263dde5a0fa70eb9a58a`
  - `tests/test_metaworld_scalability.py` — SHA-256 `cce63534bf39db2dc2842570c54df6420a6b7dc57c433082a46288fa9e19718c`
  - `tests/test_metaworld_scalability_verification.py` — SHA-256 `56abff5bd3e1960e8874225d1165c334fa7550981a541ec262008c3e29204993`

## Integrity audit

- Registered studies: 16
- Tracked evidence files: 208
- Missing registered files: 0
- Discoverable Meta-World/DCTA result files not yet assigned: 0

## Maintenance rule

Every new Meta-World experiment must receive a study ID, phase, paper role, frozen condition, method list, one-sentence result, and links to its protocol/configuration/raw output/analysis code. Re-run `python scripts/build_metaworld_dcta_experiment_ledger.py` after adding it; changed file hashes make later mutations visible.
