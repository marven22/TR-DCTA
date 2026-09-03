# Dataset and environment setup

No benchmark data are redistributed by this repository.

## MetaWorld

- Official repository: https://github.com/Farama-Foundation/Metaworld
- Documentation: https://metaworld.farama.org/

Install MetaWorld and its compatible MuJoCo stack in an isolated environment.
Record the exact upstream commit in the artifact deposit. The final code-only
TR-DCTA evaluation can operate on frozen ledgers without importing MuJoCo;
end-to-end policy regeneration cannot.

## MiniGrid / BabyAI

- Official MiniGrid repository: https://github.com/Farama-Foundation/Minigrid
- BabyAI environment documentation:
  https://minigrid.farama.org/environments/babyai/

The held-out UnlockPickup experiment uses seeds 60 through 299. Seeds, source
priors, cascade variants, missing-provenance conditions, replay budgets, and
bootstrap seeds are specified in
`configs/babyai_unlockpickup_terminal_recovery_heldout_freeze_v1.json`.

## LIBERO

- Official repository: https://github.com/Lifelong-Robot-Learning/LIBERO
- Documentation:
  https://lifelong-robot-learning.github.io/LIBERO/html/getting_started/overview.html

LIBERO was used for the MemoRepair, MemAudit, active-search, and earlier DCTA
compatibility studies. These are preserved as secondary comparisons and are not
the primary MetaWorld/BabyAI TR-DCTA terminal-recovery claim.

## Models

The semantic retrieval reconstruction uses the Hugging Face model and immutable
revision recorded in the MetaWorld configs. Model weights are downloaded from
the upstream host and are not stored here. Earlier MemoryArena generation can
optionally use the pinned Qwen checkpoint specified by the corresponding
configuration.

## AgentDojo

- Official repository: https://github.com/ethz-spylab/agentdojo

The AgentDojo evaluation uses the benchmark's official user-task and injection
task environments. This repository stores construction code and frozen
configuration identifiers, not tool environments, cached workflow traces, or
benchmark assets.

## Licensing

Researchers must accept and comply with each benchmark's current license and
download terms. The release artifact should record upstream commits and include
required notices, but it must not copy benchmark datasets into this repository.
