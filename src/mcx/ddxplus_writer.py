"""Deterministic memory writer for DDXPlus corruption archives.

The publication-v2 pipeline populates its frozen archive graph with memories
written by a pinned Qwen checkpoint.  DDXPlus reuses the same graph and the
same record shape, but composes the memory text from the dataset's own
condition and evidence metadata instead of calling a model.

Two properties make this a legitimate stand-in rather than a shortcut.  The
writer is a pure function of public task metadata, so archives regenerate
byte-identically without a GPU; and it makes the causal structure explicit
rather than hoping a sampled model produces it.  Swapping in the Qwen writer
later changes only the text, never the graph, the policies, or the labels.

Three memory kinds are produced:

``clean``
    recommends the native procedure, which the screen verified succeeds.
``harmful``
    recommends a donor procedure, which the screen verified fails; the
    behaviour changes, so the memory is contaminated *and* affected.
``reworded``
    describes the native procedure through a different pair of its findings,
    so the memory is contaminated without being behaviourally harmful.

All three share one sentence frame and differ only in which findings they
name.  An earlier revision gave harmful memories a distinctive phrase, which
let the fitted posterior rank harm at 0.99 AUC before a single replay: the
audit was solved before it started and no acquisition policy could be
distinguished from another.  The only signal now is whether the named findings
fit the patient, which is the inference the method is supposed to make.

The third kind is what makes contamination and harm separable, which is the
distinction the cascade model is fitted to.

Corruption also fails to transmit sometimes.  A memory with a corrupted parent
may still be written cleanly, in which case its two variants are byte
identical.  Without those failures contamination would equal reachability, the
contamination model would see a single class, and the posterior would be a
deterministic function of the graph rather than something to infer.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .publication_v2 import graph_spec, stable_digest


DEPTH_PHRASE = (
    "In this presentation",
    "In presentations like this one",
    "For this family of presentations",
    "As a general rule for similar presentations",
    "As a standing rule across similar consultations",
)
SHARED_PHRASE = "Across consultations that share this presentation"


def _parents(edges: Sequence[Sequence[str]]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for left, right in edges:
        values.setdefault(str(right), []).append(str(left))
    return values


def _is_harmful(task_id: str, node: str, rotation: int) -> bool:
    """Split contaminated memories into behaviourally harmful and merely reworded."""
    return stable_digest("ddxplus-harm", task_id, node, rotation)[0] % 3 != 0


def _transmits(task_id: str, node: str, rotation: int) -> bool:
    """Decide whether corruption propagates through an active parent."""
    return stable_digest("ddxplus-transmit", task_id, node, rotation)[0] % 10 < 7


def _cascade(
    candidates: Sequence[str], parents: Mapping[str, Sequence[str]],
    source: str, task_id: str, rotation: int, forced: str,
) -> set[str]:
    """Propagate corruption forward in formation order, with drop-outs.

    A memory can only be corrupted through an active parent: the origin itself,
    or a parent already corrupted.  Memories on other branches never acquire an
    active parent in this rotation, so they stay clean without special casing.
    """
    contaminated: set[str] = set()
    for node in candidates:
        active = [parent for parent in parents.get(node, ())
                  if parent == source or parent in contaminated]
        if not active:
            continue
        if node == forced or _transmits(task_id, node, rotation):
            contaminated.add(node)
    return contaminated


def plan_record(task: Mapping[str, object]) -> dict[str, object]:
    """Decide the structure of one task's archive without writing any prose.

    Every causal decision lives here: which memories corruption reaches, which
    procedure each variant recommends, which parents it cites, and which
    variants must be byte identical.  A text layer then fills in the wording.
    Both the template writer and the Qwen writer consume this same plan, so
    they differ only in prose and remain directly comparable.
    """
    task_id = str(task["task_id"])
    graph = graph_spec(task_id)
    sources = [str(value) for value in graph["source_ids"]]
    branches = [[str(node) for node in branch] for branch in graph["branch_ids"]]
    shared_ids = [str(value) for value in graph["shared_ids"]]
    edges = [(str(left), str(right)) for left, right in graph["formation_edges"]]
    parents = _parents(edges)

    native = str(task["native_policy"])
    donors = [str(donor["policy"]) for donor in task["donors"]]  # type: ignore[index]
    donor_language = [str(donor["language"]) for donor in task["donors"]]  # type: ignore[index]
    native_language = str(task["native_language"])
    native_language_alt = str(task["native_language_alt"])
    chief = str(task["chief_complaint"])
    if native in donors:
        raise ValueError(f"{task_id} lists the native procedure as a donor")

    created_at = {str(key): int(value) for key, value in graph["created_at"].items()}
    candidates = sorted((str(node) for node in graph["candidate_ids"]),
                        key=lambda node: created_at[node])
    # The first memory of the active branch always transmits and always turns
    # harmful, so every rotation has a non-empty affected set.
    states = {rotation: _cascade(candidates, parents, sources[rotation], task_id,
                                 rotation, branches[rotation][0])
              for rotation in range(3)}

    def slot(memory_id: str, container: str, variant: str, policy: str,
             language: str, *, depth: int = 0, phrase: str | None = None,
             copy_of: str | None = None) -> dict[str, object]:
        return {
            "key": f"{container}:{memory_id}:{variant}",
            "memory_id": memory_id, "container": container, "variant": variant,
            "policy": policy, "language": language, "depth": depth,
            "phrase": phrase, "copy_of": copy_of,
            # Citations must be genuine parents; masking may redact them later.
            "cited_memory_ids": sorted(parents.get(memory_id, ())),
        }

    slots: list[dict[str, object]] = []
    for index, source in enumerate(sources):
        slots.append(slot(source, "roots", "factual", donors[index],
                          donor_language[index]))
        slots.append(slot(source, "roots", "counterfactual", native, native_language))

    for branch_index, nodes in enumerate(branches):
        for depth, node in enumerate(nodes):
            phrase = DEPTH_PHRASE[min(depth, len(DEPTH_PHRASE) - 1)]
            clean_key = f"branches:{node}:counterfactual"
            slots.append(slot(node, "branches", "counterfactual", native,
                              native_language, depth=depth, phrase=phrase))
            if node not in states[branch_index]:
                # Corruption did not reach this memory, so it is written
                # exactly as it would have been without the bad origin.
                slots.append(slot(node, "branches", "factual", native,
                                  native_language, depth=depth, phrase=phrase,
                                  copy_of=clean_key))
            elif depth == 0 or _is_harmful(task_id, node, branch_index):
                slots.append(slot(node, "branches", "factual", donors[branch_index],
                                  donor_language[branch_index], depth=depth,
                                  phrase=phrase))
            else:
                slots.append(slot(node, "branches", "factual", native,
                                  native_language_alt, depth=depth, phrase=phrase))

    for node in shared_ids:
        clean_key = f"shared_memories:{node}:clean"
        slots.append(slot(node, "shared_memories", "clean", native, native_language,
                          depth=len(DEPTH_PHRASE) - 1, phrase=SHARED_PHRASE))
        for rotation in range(3):
            variant = f"active_{rotation}"
            if node not in states[rotation]:
                slots.append(slot(node, "shared_memories", variant, native,
                                  native_language, phrase=SHARED_PHRASE,
                                  depth=len(DEPTH_PHRASE) - 1, copy_of=clean_key))
            elif _is_harmful(task_id, node, rotation):
                slots.append(slot(node, "shared_memories", variant, donors[rotation],
                                  donor_language[rotation], phrase=SHARED_PHRASE,
                                  depth=len(DEPTH_PHRASE) - 1))
            else:
                slots.append(slot(node, "shared_memories", variant, native,
                                  native_language_alt, phrase=SHARED_PHRASE,
                                  depth=len(DEPTH_PHRASE) - 1))

    return {
        "task_id": task_id,
        "benchmark": str(task["benchmark"]),
        "stratum": str(task["stratum"]),
        "split": str(task["split"]),
        "target_language": str(task["target_language"]),
        "chief_complaint": chief,
        "graph": graph,
        "policy_success": {native: True, **{donor: False for donor in donors}},
        "branch_order": [list(branch) for branch in branches],
        "shared_order": list(shared_ids),
        "source_order": list(sources),
        "parents": {node: sorted(values) for node, values in parents.items()},
        "slots": slots,
    }


def silent_corrupted_memories(
    plan: Mapping[str, object], record: Mapping[str, object],
) -> list[str]:
    """Corrupted memories whose public text matches their clean counterpart.

    ``public_memory`` strips the recommended procedure, so such a memory is
    labelled harmful while being identical to a safe one in everything the
    auditor can observe.  It is an unlearnable example, not a hard one.
    """
    clean = {str(memory["memory_id"]):
             (memory["counterfactual"]["parsed"]["lesson"],
              memory["counterfactual"]["parsed"]["expected_outcome"])
             for branch in record["branches"] for memory in branch["memories"]}
    written = {str(memory["memory_id"]):
               (memory["factual"]["parsed"]["lesson"],
                memory["factual"]["parsed"]["expected_outcome"])
               for branch in record["branches"] for memory in branch["memories"]}
    silent = []
    for slot in plan["slots"]:  # type: ignore[union-attr]
        node = str(slot["memory_id"])
        if slot["copy_of"] or slot["container"] != "branches" \
                or slot["variant"] != "factual" or node not in written:
            continue
        if written[node] == clean[node]:
            silent.append(node)
    return silent


def intended_contamination(plan: Mapping[str, object], rotation: int) -> set[str]:
    """Nodes the plan intends to be corrupted in one rotation.

    Contamination is materialized by comparing a variant's text with its clean
    counterpart, so a writer that emits identical prose for both silently
    relabels a corrupted memory as clean.  Comparing this intent with the
    materialized labels catches that divergence.
    """
    intended: set[str] = set()
    for slot in plan["slots"]:  # type: ignore[union-attr]
        if slot["copy_of"]:
            continue
        container, variant = str(slot["container"]), str(slot["variant"])
        if container == "branches" and variant == "factual":
            branch = next(index for index, nodes in enumerate(plan["branch_order"])  # type: ignore[union-attr]
                          if slot["memory_id"] in nodes)
            if branch == rotation:
                intended.add(str(slot["memory_id"]))
        elif container == "shared_memories" and variant == f"active_{rotation}":
            intended.add(str(slot["memory_id"]))
    return intended


def assemble_record(
    plan: Mapping[str, object], texts: Mapping[str, tuple[str, str]], writer: str,
) -> dict[str, object]:
    """Fill a structural plan with written text and emit the archive record."""
    by_key = {str(item["key"]): item for item in plan["slots"]}  # type: ignore[index]
    parsed: dict[str, dict[str, object]] = {}
    for key, item in by_key.items():
        copy_of = item["copy_of"]
        source_key = str(copy_of) if copy_of else key
        if source_key not in texts:
            raise ValueError(f"missing generated text for slot: {source_key}")
        lesson, outcome = texts[source_key]
        parsed[key] = {"parsed": {
            "recommended_policy_id": item["policy"],
            "lesson": lesson, "expected_outcome": outcome,
            "cited_memory_ids": list(item["cited_memory_ids"]),
        }}

    roots = [{"memory_id": source,
              "factual": parsed[f"roots:{source}:factual"],
              "counterfactual": parsed[f"roots:{source}:counterfactual"]}
             for source in plan["source_order"]]  # type: ignore[index]
    branch_records = [
        {"branch_index": index,
         "memories": [{"memory_id": node,
                       "factual": parsed[f"branches:{node}:factual"],
                       "counterfactual": parsed[f"branches:{node}:counterfactual"]}
                      for node in nodes]}
        for index, nodes in enumerate(plan["branch_order"])]  # type: ignore[arg-type]
    shared_records = [
        {"memory_id": node,
         "variants": {"clean": parsed[f"shared_memories:{node}:clean"],
                      **{f"active_{rotation}":
                         parsed[f"shared_memories:{node}:active_{rotation}"]
                         for rotation in range(3)}}}
        for node in plan["shared_order"]]  # type: ignore[union-attr]

    return {
        "task_id": plan["task_id"], "benchmark": plan["benchmark"],
        "stratum": plan["stratum"], "split": plan["split"],
        "target_language": plan["target_language"], "graph": plan["graph"],
        "policy_success": plan["policy_success"], "roots": roots,
        "branches": branch_records, "shared_memories": shared_records,
        "writer": writer,
    }


# One frame for every variant. Only the named findings change, so no phrase
# distinguishes a harmful memory from a safe one.
OUTCOME = "The workup is expected to reach the diagnosis."


def template_text(plan: Mapping[str, object], slot: Mapping[str, object]) -> tuple[str, str]:
    if slot["container"] == "roots":
        return (f"A previous consultation opening with {plan['chief_complaint']} "
                f"was resolved by the {slot['language']}.", OUTCOME)
    return (f"{slot['phrase']}, use the {slot['language']}.", OUTCOME)


def build_generation_record(task: Mapping[str, object]) -> dict[str, object]:
    """Compose one task's archive using the deterministic template text."""
    plan = plan_record(task)
    texts = {str(slot["key"]): template_text(plan, slot)
             for slot in plan["slots"] if not slot["copy_of"]}  # type: ignore[index]
    return assemble_record(plan, texts, "ddxplus-template-v1")
