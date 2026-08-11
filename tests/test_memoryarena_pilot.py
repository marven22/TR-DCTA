import json
import unittest
from fractions import Fraction

import _path  # noqa: F401

from mcx.memoryarena_pilot import (
    Coefficients,
    coefficients_from_response,
    parse_json_object,
    parse_reference_coefficients,
)


class TestMemoryArenaPilotParsing(unittest.TestCase):
    def test_reference_tuple_latex_fraction(self):
        answer = r"$(c_2,c_3,c_0)=\left(-4,-2,\frac{64}{5}\right).$"
        self.assertEqual(
            parse_reference_coefficients(answer),
            Coefficients(Fraction(-4), Fraction(-2), Fraction(64, 5)),
        )

    def test_reference_assignments(self):
        answer = r"$c_2=-9,\quad c_3=-3, \quad c_0=\frac{2704}{55}.$"
        self.assertEqual(
            parse_reference_coefficients(answer),
            Coefficients(Fraction(-9), Fraction(-3), Fraction(2704, 55)),
        )

    def test_model_json_coefficients(self):
        parsed = parse_json_object(
            json.dumps({"c2": "-4", "c3": "-2", "c0": "64/5"})
        )
        self.assertEqual(
            coefficients_from_response(parsed),
            Coefficients(Fraction(-4), Fraction(-2), Fraction(64, 5)),
        )

    def test_non_json_commentary_is_rejected(self):
        with self.assertRaises(json.JSONDecodeError):
            parse_json_object('Here is the answer: {"c2": "-4"}')


if __name__ == "__main__":
    unittest.main()
