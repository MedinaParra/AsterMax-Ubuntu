import unittest

from astermax.step_units import StepUnitError, inspect_step_length_unit, require_step_mm


HEADER = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"
FOOTER = "\nENDSEC;\nEND-ISO-10303-21;\n"


class StepUnitHarnessTests(unittest.TestCase):
    def test_explicit_millimetre_step_is_accepted(self):
        text = HEADER + "#42=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));" + FOOTER
        unit = require_step_mm(text)
        self.assertEqual(unit.name, "mm")
        self.assertEqual(unit.scale_to_mm, 1.0)
        self.assertIn("LENGTH_UNIT", unit.entity)

    def test_metre_step_is_detected_but_rejected_by_mm_gate(self):
        text = HEADER + "#7=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.));" + FOOTER
        unit = inspect_step_length_unit(text)
        self.assertEqual(unit.name, "m")
        self.assertEqual(unit.scale_to_mm, 1000.0)
        with self.assertRaisesRegex(StepUnitError, "requires an explicitly millimetre-resolved STEP"):
            require_step_mm(text)

    def test_non_length_si_units_do_not_create_false_positive(self):
        text = (
            HEADER
            + "#1=(PLANE_ANGLE_UNIT() NAMED_UNIT(*) SI_UNIT($,.RADIAN.));\n"
            + "#2=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));"
            + FOOTER
        )
        self.assertEqual(require_step_mm(text).name, "mm")

    def test_conversion_based_length_unit_is_not_guessed(self):
        text = (
            HEADER
            + "#9=(LENGTH_UNIT() NAMED_UNIT(#10) CONVERSION_BASED_UNIT('INCH',#11));"
            + FOOTER
        )
        with self.assertRaisesRegex(StepUnitError, "conversion-based length unit"):
            inspect_step_length_unit(text)

    def test_ambiguous_length_units_are_rejected(self):
        text = (
            HEADER
            + "#1=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));\n"
            + "#2=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.));"
            + FOOTER
        )
        with self.assertRaisesRegex(StepUnitError, "ambiguous length units"):
            inspect_step_length_unit(text)

    def test_missing_length_unit_is_rejected(self):
        text = HEADER + "#1=CARTESIAN_POINT('',(0.,0.,0.));" + FOOTER
        with self.assertRaisesRegex(StepUnitError, "no explicit SI LENGTH_UNIT"):
            inspect_step_length_unit(text)

    def test_non_part21_text_is_rejected(self):
        with self.assertRaisesRegex(StepUnitError, "no parseable Part 21 entities"):
            inspect_step_length_unit("not a STEP data section")


if __name__ == "__main__":
    unittest.main()
