"""Unit tests for the DDXPlus domain adapter."""

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import _path  # noqa: F401

from mcx.ddxplus import (
    ConditionSpec, EvidenceSpec, PatientCase, chief_complaint, confusable_anchors,
    evidence_specificity, execute_procedure,
    iter_patients, load_conditions, load_evidences, parse_evidence_code,
    patient_presentation, policy_id, policy_success_map, procedure_succeeds,
    presentation_mentions_pathology,
    screen_case, validate_screen_config, validate_sources,
)


def evidence(name, question, meanings=None):
    return EvidenceSpec(name=name, question_en=question, data_type="B",
                        is_antecedent=False, value_meaning=meanings or {})


def condition(name, weights, severity=3):
    return ConditionSpec(name=name, severity=severity, symptoms=dict(weights),
                         antecedents={})


def patient(pathology, evidences, differential=(), case_id="case_0"):
    return PatientCase(
        case_id=case_id, age=44, sex="F", pathology=pathology,
        evidences=tuple((name, None) for name in evidences),
        initial_evidence=evidences[0] if evidences else "",
        differential=tuple(differential))


DISJOINT_CONDITIONS = {
    "alpha": condition("alpha", {"E_a0": 0.9, "E_a1": 0.8}),
    "beta": condition("beta", {"E_b0": 0.9, "E_b1": 0.8}),
    "gamma": condition("gamma", {"E_c0": 0.9, "E_c1": 0.8}),
}

DISJOINT_EVIDENCES = {
    name: evidence(name, f"does the patient report {name}?")
    for name in ("E_a0", "E_a1", "E_b0", "E_b1", "E_c0", "E_c1")
}


class ParsingTest(unittest.TestCase):
    def test_binary_and_categorical_evidence_codes(self):
        self.assertEqual(parse_evidence_code("E_55"), ("E_55", None))
        self.assertEqual(parse_evidence_code("E_55_@_V_89"), ("E_55", "V_89"))
        self.assertEqual(parse_evidence_code("E_66_@_12"), ("E_66", "12"))
        with self.assertRaises(ValueError):
            parse_evidence_code("")

    def test_release_json_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidences.json").write_text(json.dumps({
                "E_a0": {"question_en": "chest pain?", "data_type": "B",
                         "is_antecedent": False},
                "E_a1": {"question_en": "fever?", "data_type": "B",
                         "is_antecedent": True},
            }), encoding="utf-8")
            # Weights arrive as a probability mapping in the released files, but
            # a bare list and a bare float are both tolerated.
            (root / "conditions.json").write_text(json.dumps({
                "alpha": {"condition_name": "alpha", "severity": 2,
                          "symptoms": {"E_a0": {"probability": 0.9}},
                          "antecedents": {"E_a1": 0.4}},
            }), encoding="utf-8")
            evidences = load_evidences(root / "evidences.json")
            conditions = load_conditions(root / "conditions.json")
        self.assertTrue(evidences["E_a1"].is_antecedent)
        self.assertEqual(conditions["alpha"].severity, 2)
        self.assertEqual(conditions["alpha"].evidence_weights(),
                         {"E_a0": 0.9, "E_a1": 0.4})

    def test_validate_sources_rejects_dangling_evidence(self):
        with self.assertRaises(ValueError):
            validate_sources({"E_a0": evidence("E_a0", "?")}, DISJOINT_CONDITIONS)
        counts = validate_sources(DISJOINT_EVIDENCES, DISJOINT_CONDITIONS)
        self.assertEqual(counts["conditions"], 3)

    def test_patient_stream_reads_an_extensionless_zip_member(self):
        # The released archives store the CSV without a file extension.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = root / "release_train_patients.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "release_train_patients",
                    "AGE,DIFFERENTIAL_DIAGNOSIS,SEX,PATHOLOGY,EVIDENCES,INITIAL_EVIDENCE\n"
                    "18,\"[['URTI', 0.6]]\",M,URTI,\"['E_48', 'E_54_@_V_161']\",E_48\n")
            parsed = list(iter_patients(zip_path))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].pathology, "URTI")
        self.assertEqual(parsed[0].evidences, (("E_48", None), ("E_54", "V_161")))

    def test_patient_stream_reads_python_literal_columns_from_zip(self):
        rows = [{
            "AGE": "44", "SEX": "F", "PATHOLOGY": "alpha",
            # The released CSVs quote these columns as Python literals.
            "EVIDENCES": "['E_a0', 'E_a1_@_V_3']",
            "INITIAL_EVIDENCE": "E_a0",
            "DIFFERENTIAL_DIAGNOSIS": "[['alpha', 0.7], ['beta', 0.3]]",
        }]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "patients.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            zip_path = root / "patients.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.write(csv_path, arcname="patients.csv")
            parsed = list(iter_patients(zip_path))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].evidences, (("E_a0", None), ("E_a1", "V_3")))
        self.assertEqual(parsed[0].differential, (("alpha", 0.7), ("beta", 0.3)))


class ProcedureTest(unittest.TestCase):
    def test_anchored_procedure_diagnoses_its_own_patient(self):
        case = patient("alpha", ["E_a0", "E_a1"])
        self.assertEqual(execute_procedure("alpha", case, DISJOINT_CONDITIONS), "alpha")
        self.assertTrue(procedure_succeeds("alpha", case, DISJOINT_CONDITIONS))

    def test_workup_that_collects_nothing_emits_no_diagnosis(self):
        case = patient("alpha", ["E_a0", "E_a1"])
        self.assertIsNone(execute_procedure("beta", case, DISJOINT_CONDITIONS))
        self.assertFalse(procedure_succeeds("beta", case, DISJOINT_CONDITIONS))

    def test_donor_procedure_can_succeed_so_the_gate_is_empirical(self):
        # A donor whose workup collects a finding that the true pathology
        # explains best still reaches the correct diagnosis. Such cases must be
        # rejected by the screen rather than assumed away.
        conditions = {
            "alpha": condition("alpha", {"E_1": 0.9, "E_2": 0.8, "E_3": 0.7}),
            "delta": condition("delta", {"E_2": 0.6, "E_7": 0.9}),
        }
        case = patient("alpha", ["E_1", "E_2", "E_3"])
        self.assertEqual(execute_procedure("delta", case, conditions), "alpha")
        self.assertTrue(procedure_succeeds("delta", case, conditions))

    def test_anchored_procedure_can_fail_on_its_own_patient(self):
        # An atypical presentation: the only collected finding is better
        # explained by another condition, so the anchored workup misdiagnoses.
        conditions = {
            "alpha": condition("alpha", {"E_1": 0.9, "E_2": 0.3}),
            "delta": condition("delta", {"E_2": 0.95, "E_7": 0.9}),
        }
        case = patient("alpha", ["E_2"])
        self.assertEqual(execute_procedure("alpha", case, conditions), "delta")
        self.assertFalse(procedure_succeeds("alpha", case, conditions))

    def test_scoring_penalizes_findings_a_condition_cannot_explain(self):
        conditions = {
            "alpha": condition("alpha", {"E_1": 0.9, "E_2": 0.9, "E_3": 0.9}),
            "beta": condition("beta", {"E_1": 0.95}),
        }
        case = patient("alpha", ["E_1", "E_2", "E_3"])
        # Beta explains E_1 best but is contradicted by E_2 and E_3.
        self.assertEqual(execute_procedure("alpha", case, conditions), "alpha")

    def test_policy_success_map_is_keyed_by_procedure_identifier(self):
        case = patient("alpha", ["E_a0", "E_a1"])
        mapping = policy_success_map(case, ["alpha", "beta"], DISJOINT_CONDITIONS)
        self.assertEqual(set(mapping), {policy_id("alpha"), policy_id("beta")})
        self.assertTrue(mapping[policy_id("alpha")])
        self.assertFalse(mapping[policy_id("beta")])


class DonorSelectionTest(unittest.TestCase):
    def test_donors_follow_the_differential_and_exclude_the_truth(self):
        case = patient("alpha", ["E_a0"], differential=[
            ("alpha", 0.6), ("gamma", 0.3), ("beta", 0.1)])
        self.assertEqual(
            confusable_anchors(case, DISJOINT_CONDITIONS, 2), ("gamma", "beta"))

    def test_short_differentials_are_padded_deterministically(self):
        case = patient("alpha", ["E_a0"], differential=[("alpha", 1.0)])
        first = confusable_anchors(case, DISJOINT_CONDITIONS, 2)
        second = confusable_anchors(case, DISJOINT_CONDITIONS, 2)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertNotIn("alpha", first)


class PresentationTest(unittest.TestCase):
    def test_presentation_is_rendered_from_questions(self):
        case = patient("alpha", ["E_a0", "E_a1"])
        text = patient_presentation(case, DISJOINT_EVIDENCES)
        self.assertIn("44-year-old F", text)
        self.assertIn("does the patient report E_a0?", text)

    def test_presentation_cannot_depend_on_the_pathology_label(self):
        # The renderer reads observable fields only, so relabelling the record
        # must not change a single character of the target language.
        first = patient("alpha", ["E_a0", "E_a1"])
        second = PatientCase(
            case_id=first.case_id, age=first.age, sex=first.sex, pathology="beta",
            evidences=first.evidences, initial_evidence=first.initial_evidence,
            differential=first.differential)
        self.assertEqual(patient_presentation(first, DISJOINT_EVIDENCES),
                         patient_presentation(second, DISJOINT_EVIDENCES))

    def test_self_referential_antecedent_is_reported_not_fatal(self):
        # DDXPlus antecedents include questions such as "Have you ever had
        # pneumonia?", which is observable history rather than label leakage.
        evidences = {"E_a0": evidence("E_a0", "have you ever had alpha?"),
                     "E_a1": evidence("E_a1", "fever?")}
        case = patient("alpha", ["E_a0", "E_a1"])
        text = patient_presentation(case, evidences)
        self.assertTrue(presentation_mentions_pathology(text, "alpha"))
        self.assertFalse(presentation_mentions_pathology(text, "gamma"))


class SpecificityTest(unittest.TestCase):
    def test_rare_evidence_scores_above_ubiquitous_evidence(self):
        conditions = {
            "a": condition("a", {"E_rare": 1.0, "E_common": 1.0}),
            "b": condition("b", {"E_common": 1.0}),
            "c": condition("c", {"E_common": 1.0}),
        }
        scores = evidence_specificity(conditions)
        self.assertGreater(scores["E_rare"], scores["E_common"])

    def test_findings_are_ordered_by_specificity_not_alphabetically(self):
        conditions = {
            "a": condition("a", {"E_zz": 1.0, "E_aa": 1.0}),
            "b": condition("b", {"E_aa": 1.0}),
        }
        evidences = {"E_aa": evidence("E_aa", "common finding?"),
                     "E_zz": evidence("E_zz", "rare finding?"),
                     "E_chief": evidence("E_chief", "chief complaint?")}
        case = patient("a", ["E_chief", "E_aa", "E_zz"])
        text = patient_presentation(
            case, evidences, specificity=evidence_specificity(conditions))
        self.assertEqual(chief_complaint(case, evidences), "chief complaint?")
        # E_zz is rarer, so it must precede E_aa despite sorting later.
        self.assertLess(text.index("rare finding?"), text.index("common finding?"))
        # The chief complaint opens the text and is not repeated in the list.
        self.assertEqual(text.count("chief complaint?"), 1)


class ScreenConfigTest(unittest.TestCase):
    def test_frozen_thresholds_are_pinned(self):
        config = {"protocol": "ddxplus_screen_v1", "donor_count": 3,
                  "minimum_eligible_pathologies": 34}
        validate_screen_config(config)
        for key, value in (("donor_count", 2),
                           ("minimum_eligible_pathologies", 44),
                           ("protocol", "other")):
            with self.assertRaises(ValueError):
                validate_screen_config({**config, key: value})


class ScreenTest(unittest.TestCase):
    def test_eligible_case_passes_the_native_and_donor_gate(self):
        case = patient("alpha", ["E_a0", "E_a1"], differential=[
            ("alpha", 0.6), ("beta", 0.25), ("gamma", 0.15)])
        verdict = screen_case(case, DISJOINT_CONDITIONS, DISJOINT_EVIDENCES,
                              donor_count=2, minimum_evidences=2)
        self.assertTrue(verdict["eligible"])
        self.assertTrue(verdict["native_success"])
        self.assertEqual(verdict["donor_success"], [False, False])
        self.assertEqual(verdict["native_policy"], policy_id("alpha"))

    def test_case_with_too_few_findings_is_rejected(self):
        case = patient("alpha", ["E_a0"])
        verdict = screen_case(case, DISJOINT_CONDITIONS, DISJOINT_EVIDENCES,
                              donor_count=2, minimum_evidences=4)
        self.assertFalse(verdict["eligible"])
        self.assertEqual(verdict["reason"], "too few reported evidences")

    def test_unknown_pathology_is_rejected_rather_than_raising(self):
        case = patient("omega", ["E_a0", "E_a1"])
        verdict = screen_case(case, DISJOINT_CONDITIONS, DISJOINT_EVIDENCES,
                              donor_count=2, minimum_evidences=2)
        self.assertFalse(verdict["eligible"])


if __name__ == "__main__":
    unittest.main()
