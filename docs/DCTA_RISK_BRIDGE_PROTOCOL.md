# DCTA-Risk Development Bridge Protocol

## Purpose

Verify that the method selected by the exact controlled benchmark is the same executable policy used on the existing v0.4.1 archive representation.

## Frozen method

DCTA-Risk maintains the fitted directional joint posterior, conditions it on every positive and negative audit outcome, and selects

`argmax_v p_v(h) [1 + sum_{u != v} max(0, p_u(h, Z_v=1) - p_u(h))]`.

All memory weights equal one because the existing development outcome is affected-memory discovery. The transition posterior is fitted leave-one-archive-out. No held-out archive is used.

## Comparators and gate

At budget 4, compare homogeneous and local DCTA-Risk with the previously recorded ACIS-Risk, DCTA greedy, and DCTA two-step results.

This bridge is considered successful if:

1. the implementation respects the budget and conditions on both outcomes;
2. every observed truth retains posterior support;
3. the strongest DCTA-Risk variant is no more than 0.05 macro recall below ACIS-Risk.

The `0.05` competitive margin was chosen before this bridge run and is slightly larger than the previously observed `0.039` difference for DCTA local two-step. The bridge cannot establish generalization because it reuses development archives.

