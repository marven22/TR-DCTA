"""DDXPlus domain adapter: executable diagnostic procedures and case screening.

DDXPlus ships static patient records rather than a simulator, so this module
supplies the single thing the shared publication pipeline needs from any new
domain: a deterministic map from ``recommended_policy_id`` to a verified
success or failure outcome.  Everything downstream -- archive materialization,
provenance masking, source/cascade fitting, particle posteriors, and the
terminal-recovery planner -- is domain independent and is reused unchanged.

A *policy* is a diagnostic procedure anchored on one pathology.  Executing it

    1. acquires that pathology's canonical evidence set from the patient
       record, answering every queried evidence from ``EVIDENCES``;
    2. scores every condition against the acquired answers only; and
    3. emits the argmax condition, or nothing when no condition is supported.

The emitted pathology is compared with the record's ``PATHOLOGY`` field, so a
replay label is ground truth from execution.  No language model is consulted,
which preserves the ideal-binary-feedback contract the method's guarantee
assumes.

An anchored procedure can succeed on a patient it was not anchored to, and can
fail on one it was, because the decision rule reasons over whatever evidence
the workup happened to collect.  Donor failure is therefore an empirical
screening result rather than a structural artifact of the rule.

Only the public DDXPlus release files are read.  No dataset bytes are stored in
this repository; see ``docs/DATASETS.md``.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence


PROTOCOL = "memory-corruption/ddxplus-v1"

# DDXPlus encodes a categorical or multi-choice answer as ``E_55_@_V_89``.
VALUE_SEPARATOR = "_@_"

REQUIRED_PATIENT_COLUMNS = ("AGE", "SEX", "PATHOLOGY", "EVIDENCES")


def validate_screen_config(config: Mapping[str, object]) -> None:
    """Pin the frozen screen thresholds so they cannot drift silently.

    The eligible-pathology floor mirrors the Meta-World screen's declared
    proportion (35 of a 50-task population) applied to DDXPlus's 49
    pathologies.  It is a pre-declared feasibility threshold, not a value
    fitted to an observed yield.
    """
    if config.get("protocol") != "ddxplus_screen_v1":
        raise ValueError("frozen DDXPlus screen configuration required")
    if int(config.get("donor_count", 0)) != 3:
        raise ValueError("three donors are required")
    if int(config.get("minimum_eligible_pathologies", 0)) != 34:
        raise ValueError("feasibility threshold changed")


def stable_digest(*parts: object) -> bytes:
    return hashlib.sha256(
        "|".join(str(value) for value in (PROTOCOL, *parts)).encode()
    ).digest()


def stable_case_id(*parts: object) -> str:
    return "ddx_" + stable_digest(*parts).hex()[:18]


def policy_id(pathology: str) -> str:
    """Return the opaque procedure identifier recorded by a written memory."""
    return f"ddxproc::{pathology}"


def pathology_of_policy(value: str) -> str:
    if not value.startswith("ddxproc::"):
        raise ValueError(f"not a DDXPlus procedure identifier: {value}")
    return value[len("ddxproc::"):]


@dataclass(frozen=True)
class EvidenceSpec:
    name: str
    question_en: str
    data_type: str
    is_antecedent: bool
    value_meaning: Mapping[str, str]


@dataclass(frozen=True)
class ConditionSpec:
    name: str
    severity: int
    symptoms: Mapping[str, float]
    antecedents: Mapping[str, float]

    def evidence_weights(self) -> dict[str, float]:
        """Merge symptom and antecedent weights into one queried evidence set."""
        merged = dict(self.symptoms)
        for name, weight in self.antecedents.items():
            merged[name] = max(merged.get(name, 0.0), weight)
        return merged


@dataclass(frozen=True)
class PatientCase:
    case_id: str
    age: int
    sex: str
    pathology: str
    evidences: tuple[tuple[str, str | None], ...]
    initial_evidence: str
    differential: tuple[tuple[str, float], ...]

    def present(self) -> dict[str, str | None]:
        return {name: value for name, value in self.evidences}


def _literal(value: str, field: str) -> object:
    """Parse a DDXPlus list column written as JSON or as a Python literal."""
    text = (value or "").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"unparsable {field} column: {text[:80]!r}") from error


def parse_evidence_code(code: str) -> tuple[str, str | None]:
    """Split ``E_55_@_V_89`` into its evidence name and answered value."""
    name, separator, value = str(code).partition(VALUE_SEPARATOR)
    if not name:
        raise ValueError(f"empty evidence code: {code!r}")
    return name, (value if separator else None)


def _weight_map(value: object, field: str) -> dict[str, float]:
    """Accept the several shapes DDXPlus releases use for evidence weights."""
    if value in (None, ""):
        return {}
    if isinstance(value, Mapping):
        weights: dict[str, float] = {}
        for name, payload in value.items():
            if isinstance(payload, Mapping):
                probability = payload.get("probability", payload.get("proba", 1.0))
            else:
                probability = payload
            try:
                weights[str(name)] = float(probability)
            except (TypeError, ValueError):
                weights[str(name)] = 1.0
        return weights
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {str(name): 1.0 for name in value}
    raise ValueError(f"unsupported {field} container: {type(value).__name__}")


def load_evidences(path: str | Path) -> dict[str, EvidenceSpec]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("release_evidences.json must be a non-empty object")
    output: dict[str, EvidenceSpec] = {}
    for name, record in payload.items():
        meanings = record.get("value_meaning") or {}
        output[str(name)] = EvidenceSpec(
            name=str(record.get("name", name)),
            question_en=str(record.get("question_en", record.get("question_fr", name))),
            data_type=str(record.get("data_type", "B")),
            is_antecedent=bool(record.get("is_antecedent", False)),
            value_meaning={
                str(key): str((value or {}).get("en", value) if isinstance(value, Mapping)
                              else value)
                for key, value in (meanings.items() if isinstance(meanings, Mapping) else ())
            },
        )
    return output


def load_conditions(path: str | Path) -> dict[str, ConditionSpec]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("release_conditions.json must be a non-empty object")
    output: dict[str, ConditionSpec] = {}
    for name, record in payload.items():
        try:
            severity = int(record.get("severity", 0))
        except (TypeError, ValueError):
            severity = 0
        output[str(name)] = ConditionSpec(
            name=str(record.get("condition_name", name)),
            severity=severity,
            symptoms=_weight_map(record.get("symptoms"), "symptoms"),
            antecedents=_weight_map(record.get("antecedents"), "antecedents"),
        )
    return output


def validate_sources(
    evidences: Mapping[str, EvidenceSpec], conditions: Mapping[str, ConditionSpec],
) -> dict[str, int]:
    """Fail loudly when a release's shape does not match the adapter's reading."""
    if not conditions:
        raise ValueError("no conditions parsed from release_conditions.json")
    empty = sorted(name for name, spec in conditions.items() if not spec.evidence_weights())
    if empty:
        raise ValueError(
            "conditions carry no parsable evidence weights; the release shape "
            f"differs from this adapter's assumption: {empty[:5]}"
        )
    unknown = sorted({
        evidence for spec in conditions.values()
        for evidence in spec.evidence_weights()
        if evidence not in evidences
    })
    if unknown:
        raise ValueError(f"conditions reference unknown evidences: {unknown[:5]}")
    return {
        "conditions": len(conditions),
        "evidences": len(evidences),
        "antecedents": sum(spec.is_antecedent for spec in evidences.values()),
    }


def _open_patient_stream(path: Path) -> tuple[io.TextIOBase, object]:
    if path.suffix.lower() == ".zip":
        handle = zipfile.ZipFile(path)
        try:
            members = [item.filename for item in handle.infolist() if not item.is_dir()]
            # The released archives hold a single extensionless CSV member, so
            # a suffix filter is applied only to disambiguate a multi-file zip.
            named = [name for name in members if name.lower().endswith(".csv")]
            selected = named or members
            if len(selected) != 1:
                raise ValueError(
                    f"expected exactly one data member inside {path.name}: {members}")
            return io.TextIOWrapper(handle.open(selected[0]), encoding="utf-8"), handle
        except Exception:
            handle.close()
            raise
    return path.open(encoding="utf-8", newline=""), None


def iter_patients(path: str | Path, *, limit: int | None = None) -> Iterator[PatientCase]:
    """Stream patient records from a release CSV or its distributed ``.zip``.

    The released splits hold roughly a million rows each, so callers stream and
    filter rather than materializing the file.
    """
    target = Path(path)
    stream, container = _open_patient_stream(target)
    try:
        reader = csv.DictReader(stream)
        missing = [name for name in REQUIRED_PATIENT_COLUMNS
                   if name not in (reader.fieldnames or ())]
        if missing:
            raise ValueError(f"{target.name} is missing columns: {missing}")
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                return
            evidences = tuple(
                parse_evidence_code(code)
                for code in _literal(row["EVIDENCES"], "EVIDENCES")  # type: ignore[arg-type]
            )
            differential = tuple(
                (str(entry[0]), float(entry[1]))
                for entry in _literal(row.get("DIFFERENTIAL_DIAGNOSIS", ""),
                                      "DIFFERENTIAL_DIAGNOSIS")  # type: ignore[union-attr]
                if isinstance(entry, Sequence) and len(entry) >= 2
            )
            yield PatientCase(
                case_id=stable_case_id(target.name, index),
                age=int(float(row["AGE"])),
                sex=str(row["SEX"]),
                pathology=str(row["PATHOLOGY"]),
                evidences=evidences,
                initial_evidence=str(row.get("INITIAL_EVIDENCE", "")),
                differential=differential,
            )
    finally:
        stream.close()
        if container is not None:
            container.close()  # type: ignore[attr-defined]


def acquired_answers(
    patient: PatientCase, queried: Mapping[str, float],
) -> dict[str, str | None]:
    """Answer only the queried evidences; anything unasked stays unobserved."""
    return {name: value for name, value in patient.evidences if name in queried}


def execute_procedure(
    anchor: str, patient: PatientCase, conditions: Mapping[str, ConditionSpec],
    *, contradiction_penalty: float = 1.0,
) -> str | None:
    """Run the anchored workup and return the emitted pathology, if any.

    The anchor decides which evidences are collected.  The decision rule then
    scores every condition over those answers, rewarding findings the condition
    explains and penalizing findings it does not.  A workup that supports no
    condition emits nothing, which counts as a failed procedure.
    """
    if anchor not in conditions:
        raise ValueError(f"unknown anchor pathology: {anchor}")
    queried = conditions[anchor].evidence_weights()
    answers = acquired_answers(patient, queried)
    if not answers:
        return None
    # Sorted iteration with a strict improvement test makes the
    # lexicographically first condition win any score tie.
    best_name: str | None = None
    best_score = 0.0
    for name in sorted(conditions):
        weights = conditions[name].evidence_weights()
        score = sum(
            weights[evidence] if evidence in weights else -contradiction_penalty
            for evidence in answers
        )
        if best_name is None or score > best_score:
            best_name, best_score = name, score
    return best_name if best_score > 0.0 else None


def procedure_succeeds(
    anchor: str, patient: PatientCase, conditions: Mapping[str, ConditionSpec],
    *, contradiction_penalty: float = 1.0,
) -> bool:
    """Ground-truth binary outcome used as a replay label."""
    return execute_procedure(
        anchor, patient, conditions, contradiction_penalty=contradiction_penalty
    ) == patient.pathology


def policy_success_map(
    patient: PatientCase, anchors: Sequence[str],
    conditions: Mapping[str, ConditionSpec], *, contradiction_penalty: float = 1.0,
) -> dict[str, bool]:
    """Build the ``policy_success`` map consumed by ``materialize_task``."""
    return {
        policy_id(anchor): procedure_succeeds(
            anchor, patient, conditions, contradiction_penalty=contradiction_penalty
        )
        for anchor in anchors
    }


def confusable_anchors(
    patient: PatientCase, conditions: Mapping[str, ConditionSpec], count: int,
    *, evidences: Mapping[str, EvidenceSpec] | None = None,
) -> tuple[str, ...]:
    """Pick donor pathologies from the record's own differential diagnosis.

    DDXPlus ranks the plausible-but-wrong pathologies for each patient, so a
    corrupted memory recommends a confusable workup rather than an absurd one.
    The differential is padded deterministically when it is too short.

    When ``evidences`` is supplied, donors whose observable description matches
    the native procedure's, or another donor's, are skipped.  Two conditions
    can share their highest-weighted findings, and a donor that renders to the
    same text makes the corrupted memory indistinguishable from a clean one in
    everything the auditor can see, which is an unlearnable example rather than
    a hard one.
    """
    if count <= 0:
        raise ValueError("donor count must be positive")
    taken: set[str] = set()
    if evidences is not None:
        taken.add(condition_language(patient.pathology, conditions, evidences))

    def acceptable(name: str) -> bool:
        if evidences is None:
            return True
        language = condition_language(name, conditions, evidences)
        if language in taken:
            return False
        taken.add(language)
        return True

    ranked = [
        (name, probability) for name, probability in patient.differential
        if name != patient.pathology and name in conditions
    ]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    donors = [name for name, _ in ranked if acceptable(name)][:count]
    if len(donors) < count:
        remainder = sorted(
            (name for name in conditions
             if name != patient.pathology and name not in donors),
            key=lambda name: (stable_digest("donor", patient.case_id, name), name),
        )
        donors.extend(name for name in remainder if acceptable(name))
    return tuple(donors[:count])


LEADING_QUESTION = re.compile(
    r"^(?:do you have|have you ever had|have you had|have you|are you|is your|"
    r"do you|did you|does your|what is|what|how)\b[:,]?\s*", re.IGNORECASE)


def short_finding(question: str, *, limit: int = 60) -> str:
    """Reduce a DDXPlus question to the finding it asks about.

    The released questions are full interrogatives.  Splicing them verbatim
    into memory text produces long strings whose shared boilerplate dominates
    the token-overlap similarity the source estimator relies on, so the
    interrogative opening is stripped and the remainder is clipped on a word
    boundary.
    """
    text = question.strip().rstrip("?").strip()
    text = LEADING_QUESTION.sub("", text, count=1).strip()
    if not text:
        return question.strip().rstrip("?").strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
    return text


def condition_language(
    name: str, conditions: Mapping[str, ConditionSpec],
    evidences: Mapping[str, EvidenceSpec], *, top: int = 2, skip: int = 0,
) -> str:
    """Describe a procedure by the findings it looks for, never by its label.

    ``skip`` selects a later window of the same condition's findings, which
    gives a second, lexically different description of one procedure.  Memory
    variants can then differ in wording without differing in any phrase that
    betrays whether the memory is harmful.
    """
    weights = conditions[name].evidence_weights()
    ranked = sorted(weights,
                    key=lambda evidence: (-weights[evidence], evidence))[skip:skip + top]
    findings = " and ".join(short_finding(evidences[evidence].question_en)
                            for evidence in ranked if evidence in evidences)
    return f"workup for {findings}" if findings else "workup with no recorded findings"


def evidence_specificity(
    conditions: Mapping[str, ConditionSpec],
) -> dict[str, float]:
    """Score how diagnostically informative each evidence is.

    An evidence listed by one condition discriminates sharply; one listed by
    most conditions barely discriminates at all.  The score is inverse
    condition frequency, computed from the condition definitions alone, so it
    never consults a patient's label.
    """
    total = len(conditions)
    if not total:
        raise ValueError("no conditions supplied")
    counts: dict[str, int] = {}
    for spec in conditions.values():
        for name in spec.evidence_weights():
            counts[name] = counts.get(name, 0) + 1
    return {name: total / count for name, count in counts.items()}


def chief_complaint(
    patient: PatientCase, evidences: Mapping[str, EvidenceSpec],
) -> str:
    spec = evidences.get(patient.initial_evidence)
    return spec.question_en if spec is not None else "an unspecified complaint"


def patient_presentation(
    patient: PatientCase, evidences: Mapping[str, EvidenceSpec], *,
    specificity: Mapping[str, float] | None = None, top: int = 12,
) -> str:
    """Render the observable case description used as ``target_language``.

    The rendering is deterministic and reads only observable record fields, so
    the pathology label cannot be injected into the text.

    The rendered text can still name the pathology, because DDXPlus antecedents
    include self-referential history questions such as "Have you ever had
    pneumonia?".  That is real observable patient history rather than label
    leakage, so it is reported by ``presentation_mentions_pathology`` and
    counted by the screen instead of being treated as an error.
    """
    # Multi-choice evidences repeat with one row per answered value.
    grouped: dict[str, list[str]] = {}
    for name, value in patient.evidences:
        if name == patient.initial_evidence or name not in evidences:
            continue
        values = grouped.setdefault(name, [])
        if value is not None:
            values.append(value)
    rank = specificity or {}
    ordered = sorted(grouped, key=lambda name: (-rank.get(name, 0.0), name))[:top]
    reported = []
    for name in ordered:
        spec = evidences[name]
        meanings = [spec.value_meaning.get(value, value) for value in grouped[name]]
        reported.append(f"{spec.question_en} {', '.join(meanings)}" if meanings
                        else spec.question_en)
    text = (
        f"A {patient.age}-year-old {patient.sex} patient presents with "
        f"{chief_complaint(patient, evidences)} "
        f"Reported findings: {'; '.join(reported)}."
    )
    return text


def presentation_mentions_pathology(text: str, pathology: str) -> bool:
    """Report a self-referential antecedent question in a rendered case.

    Roughly a fifth of DDXPlus pathologies carry a history antecedent naming
    the condition itself.  Callers record this so the proportion is auditable,
    and may exclude such cases if a protocol requires it.
    """
    return pathology.lower() in text.lower()


def validate_task_population(
    rows: Sequence[Mapping[str, object]], *, required_donors: int = 3,
) -> dict[str, int]:
    """Check the frozen DDXPlus task population before splits are assigned.

    ``publication_v2.validate_population`` pins an exact LIBERO/Meta-World
    census, so DDXPlus is validated here instead of relaxing that frozen check.
    """
    if not rows:
        raise ValueError("empty DDXPlus task population")
    identifiers = [str(row["task_id"]) for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate task identifiers in the population")
    for row in rows:
        donors = row["donors"]
        if not isinstance(donors, Sequence) or len(donors) != required_donors:
            raise ValueError(f"{row['task_id']} does not carry {required_donors} donors")
        evidence = row["simulator_evidence"]
        if not evidence["native_success"]:  # type: ignore[index]
            raise ValueError(f"{row['task_id']} native procedure did not succeed")
        if any(evidence["donor_success"]):  # type: ignore[index]
            raise ValueError(f"{row['task_id']} has a succeeding donor procedure")
        if str(row["target_name"]) in {str(donor["name"]) for donor in donors}:
            raise ValueError(f"{row['task_id']} lists its own pathology as a donor")
    return {"tasks": len(rows),
            "donors": sum(len(row["donors"]) for row in rows)}


def screen_case(
    patient: PatientCase, conditions: Mapping[str, ConditionSpec],
    evidences: Mapping[str, EvidenceSpec], *, donor_count: int = 3,
    contradiction_penalty: float = 1.0, minimum_evidences: int = 4,
) -> dict[str, object]:
    """Apply the frozen eligibility gate to one candidate patient record.

    A case is eligible when the procedure anchored on its true pathology
    diagnoses it correctly and every confusable donor procedure fails, which
    mirrors the native-succeeds / donors-fail contract used by the existing
    robotics screens.
    """
    if patient.pathology not in conditions:
        return {"case_id": patient.case_id, "eligible": False,
                "reason": "pathology absent from release_conditions.json"}
    if len(patient.evidences) < minimum_evidences:
        return {"case_id": patient.case_id, "eligible": False,
                "reason": "too few reported evidences"}
    native_success = procedure_succeeds(
        patient.pathology, patient, conditions,
        contradiction_penalty=contradiction_penalty)
    donors = confusable_anchors(patient, conditions, donor_count, evidences=evidences)
    donor_success = [
        procedure_succeeds(donor, patient, conditions,
                           contradiction_penalty=contradiction_penalty)
        for donor in donors
    ]
    eligible = (native_success and not any(donor_success)
                and len(donors) == donor_count)
    return {
        "case_id": patient.case_id,
        "pathology": patient.pathology,
        "native_policy": policy_id(patient.pathology),
        "native_success": native_success,
        "donors": [
            {"policy": policy_id(donor), "name": donor,
             "language": condition_language(donor, conditions, evidences)}
            for donor in donors
        ],
        "donor_success": donor_success,
        "eligible": eligible,
        "reason": "" if eligible else (
            "anchored procedure failed on its own patient" if not native_success
            else "too few distinguishable donor procedures" if len(donors) != donor_count
            else "a donor procedure diagnosed the patient correctly"),
        "evidence_count": len(patient.evidences),
        "differential_length": len(patient.differential),
        "severity": conditions[patient.pathology].severity,
    }
