# BabyAI/MiniGrid go/no-go results v1

## Decision

Structural decision: `GO`.

BabyAI/MiniGrid passes as a feasible second domain for the paper, with one
important qualification: it is a symbolic, language-conditioned domain. It
should complement MetaWorld rather than replace it.

## Setup

The audit used the official `BabyAI-OpenDoorColor-v0` environment from
MiniGrid 3.0.0. Each context is a deterministic seed with a mission such as
`open the purple door`.

The archive contains reusable strategy memories:

- open the red door
- open the green door
- open the blue door
- open the purple door
- open the yellow door
- open the grey door

Each color family has three descendants: nearest matching door, farthest
matching door, and middle-ranked matching door. Every memory is executed in the
real BabyAI/MiniGrid environment.

## Results

Artifact: `reports/babyai_minigrid_go_no_go_v1.json`

Verification: `reports/babyai_minigrid_go_no_go_verified_v1.json`

Counts:

- contexts: 60
- target colors represented: 6
- executable outcomes: 1080
- execution errors: 0
- local correct outcomes: 180
- family-target transfers: 300
- harmful family-target transfers: 300
- targets with harm: 60
- targets with recovery: 60
- harmful source colors: 6

All go/no-go gates passed.

Target color distribution:

- purple: 13
- green: 8
- yellow: 17
- grey: 10
- blue: 5
- red: 7

## Interpretation

This benchmark gives us the structure missing from the failed second-domain
attempts:

- locally correct memories exist: the correct color strategies solve their
  matching missions
- harmful transfer exists: a mismatched color strategy fails the target mission
- recovery exists: the three correct-color descendants remain successful
- corruption is selective: harm is tied to the transferred color family
- execution is cheap and deterministic

In simple terms, a memory like `open the purple door` is correct when the
mission is `open the purple door`, but harmful when the mission is `open the
green door`. Filtering the purple-door family leaves green-door strategies that
recover the task.

## Limitation

The current v1 audit is intentionally clean and symbolic. That is useful for
theory alignment, but it may be too easy if presented alone. For the paper, the
right framing is:

MetaWorld tests causal memory corruption in continuous embodied control.
BabyAI/MiniGrid tests the same mechanism in symbolic language-conditioned
agents where the causal structure is explicit.

The next step is to run the paper-facing method matrix on this BabyAI/MiniGrid
archive construction, including SC-DCTA, ablations, and baselines.
