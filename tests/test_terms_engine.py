import unittest

from terms_engine import (
    PRE_CONSTRUCTION_EXTENSION,
    PRE_CONSTRUCTION_START,
    generate_terms,
    number_to_words,
    parse_terms_defaults,
    resolve_delivery_stage_for_unit,
    validate_terms_values,
)


SAMPLE_TERMS = """Payment Installments will be through post-dated cheques as Follows:
40% down payment to be paid upon approval
60% over equally 24 monthly installments through Post dated Cheques.
Please note that proceeding with any work on-site is strictly contingent upon the client delivering all post-dated installment cheques.
Validity of Offer: This offer is valid for a period of seven (7) days from the date of issuance.
Start Date: The project commencement date shall be (45) calendar days following the payment date.
End Date: The project completion date shall be (120) calendar days from the start date, considering the construction sequence
Grace Period: A grace period of (30) calendar days will be granted following the end date.
Unrelated Clause: This text must remain exactly unchanged."""


class TermsEngineTests(unittest.TestCase):
    def build(self, **overrides):
        values = {
            "delivery_stage": "Post-Delivery",
            "duration_months": 4,
            "payment_method": "Post-Dated Cheques",
            "custom_payment_method": "",
            "down_payment_percent": 40,
            "due_event": "Upon Approval",
            "custom_due_event": "",
            "payment_term_months": 24,
            "installment_frequency": "Monthly",
            "offer_validity_days": 7,
        }
        values.update(overrides)
        return generate_terms(SAMPLE_TERMS, **values)

    def test_parses_existing_defaults(self):
        defaults, warnings = parse_terms_defaults(SAMPLE_TERMS)
        self.assertEqual(defaults.payment_method, "Post-Dated Cheques")
        self.assertEqual(defaults.down_payment_percent, 40)
        self.assertEqual(defaults.payment_term_months, 24)
        self.assertEqual(defaults.installment_frequency, "Monthly")
        self.assertEqual(defaults.offer_validity_days, 7)
        self.assertEqual(defaults.duration_months, 4)
        self.assertEqual(warnings, [])

    def test_unit_id_controls_delivery_stage_default(self):
        self.assertEqual(
            resolve_delivery_stage_for_unit("OW/HV1-4D", "Post-Delivery"),
            "Pre-Construction",
        )
        self.assertEqual(
            resolve_delivery_stage_for_unit("OW/QV1-32-VB", "Post-Delivery"),
            "Pre-Construction",
        )
        for unit_id in ("OW/RV2-30-VB", "OW/RA4-50-4-14", "OW/QA1-1"):
            self.assertEqual(
                resolve_delivery_stage_for_unit(unit_id, "Post-Delivery"),
                "Post-Delivery",
            )

    def test_acceptance_example_monthly(self):
        terms, values = self.build(
            delivery_stage="Pre-Construction",
            duration_months=6,
            down_payment_percent=40,
            payment_term_months=24,
        )
        self.assertIn("40% down payment to be paid upon approval.", terms)
        self.assertIn("60% over 24 equal monthly installments through post-dated cheques.", terms)
        self.assertIn("seven (7) days", terms)
        self.assertIn(PRE_CONSTRUCTION_START, terms)
        self.assertIn(PRE_CONSTRUCTION_EXTENSION.format(months=6), terms)
        self.assertEqual(values["calculatedInstallmentCount"], 24)
        self.assertEqual(values["calculatedRemainingBalancePercent"], 60)

    def test_acceptance_example_six_months(self):
        terms, values = self.build(down_payment_percent=30, payment_term_months=6)
        self.assertIn("70% over 6 equal monthly installments", terms)
        self.assertEqual(values["calculatedInstallmentCount"], 6)

    def test_acceptance_example_quarterly(self):
        terms, values = self.build(
            down_payment_percent=25,
            payment_term_months=24,
            installment_frequency="Quarterly",
        )
        self.assertIn("75% over 8 equal quarterly installments", terms)
        self.assertEqual(values["calculatedInstallmentCount"], 8)

    def test_post_delivery_preserves_wording_and_updates_days(self):
        terms, _ = self.build(duration_months=6)
        self.assertIn(
            "End Date: The project completion date shall be (180) calendar days "
            "from the start date, considering the construction sequence",
            terms,
        )
        self.assertIn(
            "Start Date: The project commencement date shall be (45) calendar days "
            "following the payment date.",
            terms,
        )

    def test_unrelated_terms_are_preserved_and_clauses_not_duplicated(self):
        terms, _ = self.build(down_payment_percent=30, payment_term_months=6)
        self.assertIn("Unrelated Clause: This text must remain exactly unchanged.", terms)
        self.assertEqual(terms.count("Payment installments will be through"), 1)
        self.assertEqual(terms.count("Validity of Offer:"), 1)

    def test_quarterly_term_validation(self):
        errors = validate_terms_values(3, 25, 10, "Quarterly", 7)
        self.assertIn("Quarterly payment terms must be divisible by 3.", errors)

    def test_number_to_words_range(self):
        self.assertEqual(number_to_words(1), "one")
        self.assertEqual(number_to_words(21), "twenty-one")
        self.assertEqual(number_to_words(365), "three hundred sixty-five")
        with self.assertRaises(ValueError):
            number_to_words(366)


if __name__ == "__main__":
    unittest.main()
