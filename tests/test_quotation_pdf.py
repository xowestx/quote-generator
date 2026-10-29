import io
import unittest
from pathlib import Path

from pypdf import PdfReader

from quotation_pdf import (
    PaymentPlan,
    QuotationData,
    amount_in_words,
    build_quotation_pdf,
    parse_terms,
)

ROOT = Path(__file__).resolve().parents[1]

TERMS = """Payment installments will be through post-dated cheques as follows:
30% down payment to be paid upon approval.
70% over 6 equal monthly installments through post-dated cheques.
Validity of Offer: This offer is valid for a period of seven (7) days from the date of issuance.
End Date: The project completion date shall be (60) calendar days from the start date.
Grace Period: A grace period of (15) calendar days will be granted following the end date."""


def _text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text() for page in reader.pages]


def _quote(**overrides):
    data = dict(
        unit_id="OW/RA2-19-3-20",
        client_name="Sherry Tharwat Riad Ahmed Elgendy",
        request_type="Interior Modification",
        date_text="28-Oct-2026",
        ref_no="1778",
        items=[{"description": "Interior modification works – as per BOQ “if any”.",
                "unit": "L.S.", "qty": 1, "rate": 55547.65}],
        terms_text=TERMS,
        payment=PaymentPlan(30, "Upon Approval", 6, "monthly"),
    )
    data.update(overrides)
    return QuotationData(**data)


class AmountInWordsTests(unittest.TestCase):
    def test_quotation_1778_total(self):
        self.assertEqual(
            amount_in_words(63324.32),
            "Sixty Three Thousand Three Hundred Twenty Four Egyptian Pounds "
            "and Thirty Two Piasters Only",
        )

    def test_whole_pounds_and_millions(self):
        self.assertEqual(amount_in_words(1_000_000), "One Million Egyptian Pounds Only")


class TermsParsingTests(unittest.TestCase):
    def test_payment_lines_are_one_clause(self):
        terms = parse_terms(TERMS)
        self.assertEqual(terms[0]["heading"], "Payment")
        self.assertIn("30% down payment", terms[0]["body"])
        self.assertIn("70% over 6 equal monthly", terms[0]["body"])
        self.assertEqual([t["heading"] for t in terms[1:]],
                         ["Validity of Offer", "End Date", "Grace Period"])

    def test_numbered_and_bulleted_lines(self):
        terms = parse_terms("1. Validity of Offer: seven days.\n- Grace Period: 15 days.")
        self.assertEqual([t["heading"] for t in terms], ["Validity of Offer", "Grace Period"])


class QuotationPdfTests(unittest.TestCase):
    def test_pages_totals_and_payment_plan(self):
        pages = _text(build_quotation_pdf(_quote()))
        self.assertEqual(len(pages), 2)  # quotation + bank details
        first = pages[0]
        for expected in ("55,547.65", "7,776.67", "63,324.32", "1778",
                         "18,997.30", "44,327.02", "6 monthly instalments of 7,387.84 EGP",
                         "OW/RA2-19-3-20"):
            self.assertIn(expected, first)
        self.assertIn("EG810010000700000100073973637", pages[1])
        self.assertIn("Attachment to quotation 1778", pages[1])

    def test_full_down_payment_shows_no_instalments(self):
        first = _text(build_quotation_pdf(_quote(payment=PaymentPlan(100, "Upon Approval"))))[0]
        self.assertIn("No instalments", first)

    def test_land_extension_has_no_vat(self):
        first = _text(build_quotation_pdf(_quote(vat_rate=0.0)))[0]
        self.assertNotIn("VAT", first)
        self.assertIn("Total (Egyptian Pounds)", first)

    def test_detailed_scope_adds_boq_page(self):
        scope = [{"No.": "", "Item": "HVAC WORKS", "Row Type": "section"},
                 {"No.": "1.1", "Item": "Refrigerant pipes", "Unit": "m", "QTY": 12,
                  "Rate": 950, "Total (EGP)": 11400, "Row Type": "item"}]
        pages = _text(build_quotation_pdf(_quote(detailed_scope_items=scope, scope_label="HVAC Works")))
        self.assertEqual(len(pages), 3)
        self.assertIn("11,400.00", pages[2])

    def test_many_items_flow_onto_extra_pages(self):
        items = [{"description": f"Item {i} " + "long description " * 12,
                  "unit": "No.", "qty": i, "rate": 1000} for i in range(1, 26)]
        pages = _text(build_quotation_pdf(_quote(items=items)))
        self.assertGreater(len(pages), 3)
        joined = "".join(pages)
        self.assertIn("Item 25", joined)
        self.assertIn("370,500.00", joined)  # 325,000 + 14% VAT

    def test_appended_pdfs(self):
        extra = build_quotation_pdf(_quote())
        pages = _text(build_quotation_pdf(_quote(), append_pdfs=[extra]))
        self.assertEqual(len(pages), 4)

    def test_assets_are_bundled(self):
        for rel in ("assets/fonts/Poppins-Regular.ttf", "assets/fonts/Poppins-Medium.ttf",
                    "assets/fonts/Poppins-Bold.ttf", "assets/logos/oplus_logo_white.png",
                    "assets/logos/owest_orascom_white.png"):
            self.assertTrue((ROOT / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
