# Prob-DCTA Go/No-Go Protocol v0.1

## Status

Frozen before inspecting benchmark outcomes. Any changes after the first run are exploratory and receive a new protocol version.

## Question

Does jointly maintaining uncertainty over a corruption origin and its possible descendants improve budgeted harmful-memory discovery over committing to one likely origin first?

## Controlled setting

- Three structurally matched candidate origins (`sa`, `sb`, `sc`).
- Exactly one latent origin per world.
- Three replayable descendants per origin, with identical branch structure.
- Origin records are treated as quarantined forensic candidates and are not replayable. This holds the descendant-audit budget constant across methods.
- Four propagation levels vary gateway and downstream transmission probabilities.
- Budget: four descendant replays from nine candidates.
- Harm weights increase with cascade depth: 1, 2, and 3.
- All worlds and replay outcomes are enumerated exactly; there is no Monte Carlo error.

## Source-information conditions

For each propagation level, all three possible forensic signals are evaluated under:

1. known origin: posterior confidence 1.00;
2. high confidence: 0.75 on the signaled origin;
3. medium confidence: 0.50;
4. uniform uncertainty: 1/3;
5. wrong60 stress test: the model assigns 0.60 to the signaled origin, but its true probability is 0.20.

The first four conditions are calibrated. The fifth is deliberately misspecified and is not part of the primary success gate.

## Frozen comparators

- Static Risk: no posterior update.
- Positive-only Risk: ignores negative replay evidence.
- DCTA-Top1: commits to the maximum-prior origin and cannot restore discarded source support.
- Source-IG: chooses every replay for expected source-entropy reduction.
- Source-then-DCTA: one information-gain replay followed by DCTA-Risk.
- ENS: unchanged exact sequential ENS on the same joint posterior.
- Prob-DCTA: unchanged DCTA-Risk acquisition with full joint origin/descendant conditioning.
- Exact Bayes oracle: upper reference under the true finite-world distribution.

## Primary metrics

- expected weighted harmful-memory discoveries;
- expected harmful-memory recall;
- source top-1 accuracy;
- source Brier score and posterior entropy;
- oracle regret.

## Go/no-go gate

Prob-DCTA becomes the proposed primary extension only if all conditions hold:

1. Exact reduction: Prob-DCTA and DCTA-Top1 are numerically identical when origin confidence is 1.00.
2. Ambiguous-origin utility: pooled weighted utility over the 0.75, 0.50, and uniform conditions is strictly above DCTA-Top1 and Positive-only Risk.
3. Materiality: Prob-DCTA closes at least 20% of the DCTA-Top1-to-oracle utility gap over those ambiguous conditions.
4. Strong prior-aware comparison: Prob-DCTA is no worse than ENS by more than 0.02 weighted utility when pooled over ambiguous conditions.
5. Localization is not cosmetic: Prob-DCTA's final source Brier score is lower than its initial-prior Brier score over ambiguous conditions.

The wrong60 condition establishes a failure boundary. It is reported separately and cannot rescue a failed primary gate.

## Interpretation

Passing justifies a full realistic multi-root archive study. Failing means the latent-origin formulation remains a robustness analysis or motivates a different acquisition rule; it does not invalidate known-origin DCTA.

