# Frozen BabyAI/MiniGrid go/no-go v1

Status: frozen after planner smoke tests and before the full transfer matrix.

## Purpose

Determine whether BabyAI/MiniGrid can serve as a credible second domain for the
paper's causal memory-corruption experiments. This is a structural audit only.
It does not run SC-DCTA, DCTA, ENS, active search, MemAudit, or any comparator.

## Executable substrate

The audit uses MiniGrid 3.0.0 and Gymnasium 1.1.1 with the official
`BabyAI-OpenDoorColor-v0` environment. Each context is a deterministic seed and
mission such as `open the purple door`.

## Memory construction

A memory is a reusable symbolic strategy: open a door of a particular color.
For each color, three deterministic variants are used: nearest matching door,
farthest matching door, and middle-ranked matching door. These variants create
multiple descendants per source strategy.

The audit uses six color families: red, green, blue, purple, yellow, and grey.
For a target mission asking for color `c`, the three `c` memories are locally
correct if they complete the mission. A mismatched color family is a candidate
corrupted source family for that target.

## Transfer and harm

Every color-variant memory is executed on every selected context. A transfer is
harmful when a mismatched color strategy fails the target mission while at least
three correct-color strategies succeed on the same target. This directly tests
recoverability: filtering the mismatched source family must leave successful
alternatives.

## Go/no-go gates

The audit passes only if 60 contexts complete, at least four target colors are
represented, all 1080 executions finish without errors, all 180 matching
color-strategy executions are locally correct, at least 180 mismatched
family-target transfers are harmful, at least 50 targets show harm, at least 50
targets retain three recovery alternatives, harmful transfers span at least four
source colors, and 12 repeat checks match exactly.

Passing this audit only licenses later method experiments. It is not evidence
that SC-DCTA works on BabyAI/MiniGrid.
