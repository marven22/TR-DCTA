# Statistical protocol

## Endpoint

The primary endpoint is terminal safe recovery,

\[
\mathrm{SR}=\mathbf{1}\{A\subseteq Q\},
\]

where `A` is the realized harmful cascade and `Q` is the final quarantine set.
The reported percentage is the mean of `100 * SR` over the stated evaluation
population.

## Matched comparisons

For RQ1 and matched direct-policy comparisons in RQ2, uncertainty is computed
for the paired unit-level difference,

\[
\mathrm{SR}_{\mathrm{LANTERN}}-\mathrm{SR}_{\mathrm{baseline}}.
\]

We use 10,000 nonparametric cluster-bootstrap draws. A draw resamples clusters
with replacement and retains the outcomes of both methods for every selected
cluster. MetaWorld clusters are held-out tasks. BabyAI clusters are held-out
contexts. AgentDojo clusters are held-out workflows or frozen task clusters,
according to the corresponding protocol. Episodes, source rotations, and
mask replicates inside a cluster are first aggregated and are not treated as
independent samples.

The 2.5th and 97.5th empirical percentiles form the paired 95% interval. An
interval above zero means that the resampled LANTERN advantage over that
matched comparator remains positive. It is not a claim about an unmatched
external method.

## External comparisons

RQ3 compares LANTERN with GraphAS, MemAudit, and MemoRepair. These methods
can differ in source information, replay versus exhaustive audit access, and
quarantine versus direct-repair intervention. We report their recovery values
with their replay, audit, or repair cost. Paired bootstrap inference is shown
only where the methods share both an evaluation population and a sufficiently
matched contract.

## Reproduction

Run the corresponding frozen runner, then its verifier. The RQ1 aggregate can
be regenerated with:

```bash
python paper_results/rq1_paired_bootstrap_95_v1.py
```

The script records SHA-256 hashes of its input outcome reports in the resulting
JSON file. A hash mismatch indicates that the result is not the frozen paper
analysis.
