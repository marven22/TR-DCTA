# Publication v2 External Robotics Extension Protocol

Status: frozen before Meta-World policy-transfer screening  
Protocol: `memory-corruption/multi-origin-publication-v2/external-extension`

## Trigger

The frozen held-out LIBERO screen produced 20 eligible targets, below the required 24, and 90% of eligible targets came from `libero_90`, above the 75% cap. The LIBERO-only production gate therefore failed and may not be weakened.

## External benchmark

Add Meta-World 3.0.0 as an independent simulator stratum:

- official PyPI release `metaworld==3.0.0`;
- 50 distinct MuJoCo manipulation tasks;
- one official scripted expert policy per task through `ENV_POLICY_MAP`;
- `mujoco==3.11.0`, `gymnasium==1.3.0`, Python 3.11;
- headless physics-only execution.

No Meta-World task, trajectory, memory, or outcome has previously influenced method development in this repository.

## Frozen screen

For every one of the 50 task environments:

1. evaluate its matching official expert policy at seeds 1101, 2202, and 3303;
2. run the full environment horizon and record whether success occurs at least once;
3. retain the target only if the native expert succeeds at all three seeds;
4. order the other 49 policies by SHA-256 of protocol, target, and donor;
5. evaluate donors on the target environment at the same three seeds;
6. a donor is eligible only if it emits valid finite actions and fails at all three seeds;
7. stop after three eligible donors or exhaust all policies.

The Meta-World gate requires at least 35 targets with a successful native policy and three verified failing donors. The threshold cannot be lowered after screening.

## Production population if the gate passes

The final v2 dataset combines:

- the 20 strictly eligible held-out LIBERO tasks as a language-conditioned stratum;
- all eligible Meta-World tasks as an independent manipulation stratum.

Splits are made by underlying task within benchmark. Development and validation may be used for Qwen-generation QA and observable-prior calibration; the test tasks are label-joined once after method code is frozen.

Every Meta-World archive follows the same v2 memory design as LIBERO: three independently verified donor origins, five descendants per origin, shared merge/bridge/revival nodes, incomplete provenance, one hash-selected primary active origin, and paired Qwen2.5-14B factual/corrected memory generation.

Simulator success remains private. The memory writer never judges policy success.

## Cross-benchmark claims

Results must be reported separately for LIBERO and Meta-World before any pooled estimate. A pooled task-cluster estimate is secondary. Passing in one benchmark cannot hide failure in the other.

The final primary claim requires Prob-DCTA to beat DCTA-Top1 in each benchmark and in the pooled task-cluster analysis. Noninferiority to ENS and source-calibration improvement are evaluated per benchmark.

