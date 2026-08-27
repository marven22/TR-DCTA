# Literature review candidates for TR-DCTA

Twenty-five papers grouped by the role they play in the argument. The
`Checked` column records whether the citation was confirmed against a live
search during compilation; unchecked entries are well known but their venue and
author list should be confirmed before submission.

## 1. Active search — the lineage the ENS baseline comes from

`src/mcx/active_search_baselines.py` implements the ENS acquisition rule and
Graph Active Search. This is their citation chain, in order.

| # | Paper | Venue | Why it matters | Checked |
|---|---|---|---|:-:|
| 1 | Garnett et al., *Bayesian Optimal Active Search and Surveying* | ICML 2012 | Founding formulation of budgeted search for rare positives | ✓ |
| 2 | Wang, Garnett & Schneider, *Active Search on Graphs* | KDD 2013 | The Graph Active Search baseline in `BASELINE_PROVENANCE.md` | ✓ |
| 3 | Jiang et al., *Efficient Nonmyopic Active Search* | ICML 2017 | **The ENS baseline.** Budget-aware nonmyopic acquisition; proves no polynomial policy has a nontrivial approximation ratio | ✓ |
| 4 | Jiang et al., *Efficient Nonmyopic Batch Active Search* | NeurIPS 2018 | Batch extension; relevant if you ever replay more than one memory at a time | ✓ |
| 5 | Nguyen et al., *Nonmyopic Multiclass Active Search with Diminishing Returns* | AISTATS 2023 | Diminishing-returns utilities; closest existing work to a non-count objective | ✓ |
| 6 | *Nonmyopic Multifidelity Active Search* (arXiv 2106.06356) | — | Cheap-vs-expensive observations, analogous to text inspection vs physical replay | ✓ |

**The gap you are filling.** Every paper above maximises *what the search
finds*. None optimises a terminal decision taken after the budget is spent.
That is the sentence your contribution turns on.

## 2. Sequential decision theory — why the rollout construction is principled

| # | Paper | Venue | Why it matters | Checked |
|---|---|---|---|:-:|
| 7 | Bertsekas, *Rollout Algorithms for Discrete Optimization: A Survey* | Springer 2013 | TR-DCTA is exactly rollout policy improvement over base DCTA; this is the citation for your dominance proof | ✓ |
| 8 | Bertsekas, *Dynamic Programming and Suboptimal Control: A Survey from ADP to MPC* | Eur. J. Control 2005 | Situates rollout among lookahead methods | ✓ |
| 9 | Chaloner & Verdinelli, *Bayesian Experimental Design: A Review* | Statistical Science 1995 | Canonical decision-theoretic framing of "which experiment next" | ✓ |
| 10 | Lindley, *On a Measure of the Information Provided by an Experiment* | Ann. Math. Statist. 1956 | Origin of expected information gain, which your `source_ig` baseline instantiates | |
| 11 | Rainforth et al., *Modern Bayesian Experimental Design* | Statistical Science 2024 | Current survey; positions your work against amortised BED | ✓ |
| 12 | Blau et al., *Optimizing Sequential Experimental Design with Deep RL* | ICML 2022 | Treats design as an MDP; the closest methodological neighbour outside memory auditing | ✓ |

## 3. Agent memory systems — where corrupted memories come from

| # | Paper | Venue | Why it matters | Checked |
|---|---|---|---|:-:|
| 13 | Park et al., *Generative Agents* | UIST 2023 | Memory stream plus reflection: the write-then-reuse loop your threat model assumes | |
| 14 | Shinn et al., *Reflexion* | NeurIPS 2023 | Verbal self-critique stored for later runs; a corrupted reflection is your source memory | |
| 15 | Packer et al., *MemGPT* | arXiv 2310.08560 | Memory as an OS with explicit paging; motivates persistence | |
| 16 | Zhao et al., *ExpeL: LLM Agents Are Experiential Learners* | AAAI 2024 | Cross-task experience reuse, i.e. how corruption propagates between tasks | |
| 17 | Xu et al., *A-MEM: Agentic Memory for LLM Agents* | arXiv 2502.12110 | Memories link to prior memories and trigger updates — an explicit provenance graph | ✓ |
| 18 | Chhikara et al., *Mem0* | arXiv 2504.19413 | Production long-term memory; supports the deployment framing | ✓ |

## 4. Memory and RAG poisoning — the threat model

| # | Paper | Venue | Why it matters | Checked |
|---|---|---|---|:-:|
| 19 | Zou et al., *PoisonedRAG* | USENIX Security 2025 | First knowledge-corruption attack on RAG; 90% success from five injected texts | ✓ |
| 20 | Chen et al., *AgentPoison* | NeurIPS 2024 | Backdoors an agent's long-term memory; ≥80% success at <0.1% poison rate | ✓ |
| 21 | *MINJA: Memory Injection Attacks via Query-Only Interaction* (arXiv 2503.03704) | NeurIPS 2025 | Poisoning by ordinary queries alone — no privileged access, so any user is a threat | ✓ |
| 22 | *Memory Poisoning Attack and Defense on Memory-Based LLM Agents* (arXiv 2601.05504) | — | Pairs attack with defence; a natural comparison point | ✓ |
| 23 | *MemSecBench: Tracking Agent Memory Poisoning from Persistence to Consequence and Repair* (arXiv 2607.27080) | — | Benchmarks persistence and repair — closest existing evaluation to yours | ✓ |

## 5. Memory auditing and repair — your direct competitors

| # | Paper | Venue | Why it matters | Checked |
|---|---|---|---|:-:|
| 24 | *MemAudit: Post-hoc Auditing of Poisoned Agent Memory* (arXiv 2605.23723) | — | **Reconstructed in `src/mcx/memaudit.py`.** Counterfactual influence plus a memory consistency graph; post-hoc, no budgeted acquisition | ✓ |
| 25 | *MemoRepair: Barrier-First Cascade Repair in Agentic Memory* (arXiv 2605.07242) | — | **Reconstructed in `src/mcx/memorepair.py`.** Withdrawal, republication and validation *given* a repair scope — complementary, since you spend budget discovering that scope | ✓ |
| 26 | *Causal Intervention-Based Memory Selection for Long-Horizon LLM Agents* (arXiv 2605.17641) | — | Risk-aware intervention scoring under a memory budget; the nearest thing found to your ACIS-Risk baseline | ✓ |
| 27 | *From Faulty Memories to Corrected Actions: Dependency-Guided Rollback Repair* (arXiv 2608.10502) | — | Dependency-guided rollback, i.e. provenance-aware repair | ✓ |

## 6. Benchmarks used

| # | Paper | Venue | Checked |
|---|---|---|:-:|
| 28 | Chevalier-Boisvert et al., *BabyAI* (arXiv 1810.08272) | ICLR 2019 | ✓ |
| 29 | Yu et al., *Meta-World* (arXiv 1910.10897) | CoRL 2019 | ✓ |
| 30 | Liu et al., *LIBERO* | NeurIPS 2023 | ✓ |
| 31 | Fansi Tchango et al., *DDXPlus* (arXiv 2205.09148) | NeurIPS 2022 Datasets & Benchmarks | ✓ |

## Open item: ACIS-Risk has no located source

`docs/BASELINE_PROVENANCE.md` lists ACIS-Risk as a "frozen predecessor
implemented here", and `src/mcx/risk_aware_acis.py` implements it. No external
paper matching that acronym was found. Either it is internal to this project —
in which case the provenance table should say so explicitly, as it does for the
DCTA ablations — or the original citation needs recovering. A reviewer checking
the baseline table will hit this first.

## How to deploy these in the write-up

The strongest framing runs in three moves. Sections 1 and 2 establish that
budgeted acquisition is a mature field that has consistently optimised
*discovery*. Sections 3 and 4 establish that persistent agent memory is now
real and demonstrably attackable, so the problem is not hypothetical. Section 5
shows that existing auditing and repair work is either post-hoc or assumes the
repair scope is already known.

TR-DCTA sits in the space none of them occupy: spending a physical budget to
discover the scope, while optimising the recovery decision rather than the
discovery count. Papers 3, 24 and 25 are the three a reviewer will most want
you to have distinguished yourself from.
