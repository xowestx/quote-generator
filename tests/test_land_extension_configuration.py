import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


class LandExtensionConfigurationTests(unittest.TestCase):
    def test_payment_term_defaults_to_48_monthly_installments(self):
        self.assertIn(
            '48\n                if selected_request_type == "Land Extension"',
            APP_SOURCE,
        )
        self.assertIn(
            '"Monthly"\n                if selected_request_type == "Land Extension"',
            APP_SOURCE,
        )

    def test_payment_term_control_remains_editable(self):
        payment_widget = APP_SOURCE.split(
            'st.number_input(\n                "Payment Term (Months)"', 1
        )[1].split(")", 1)[0]
        self.assertNotIn('disabled=selected_request_type == "Land Extension"', payment_widget)


if __name__ == "__main__":
    unittest.main()
