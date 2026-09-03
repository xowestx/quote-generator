import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


class PdfPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview_source = APP_SOURCE.split(
            "            with col_export2:",
            1,
        )[1].split(
            "            # Document Hub Display",
            1,
        )[0]

    def test_safe_text_helper_is_defined_before_pdf_rows(self):
        self.assertLess(
            self.preview_source.index("def pdf_safe_text(value):"),
            self.preview_source.index("for _, item_row in summary_df.iterrows():"),
        )

    def test_dynamic_pdf_cells_are_sanitized(self):
        for dynamic_value in (
            "final_client_name",
            "selected_unit",
            "disp_req_name",
            "item_row.get('Description', '')",
            "item_row.get('Unit', '')",
            "item_row.get('QTY', '')",
        ):
            self.assertIn(dynamic_value, self.preview_source)
        self.assertIn(
            "pdf_safe_text(item_row.get('Description', ''))[:45]",
            self.preview_source,
        )
        self.assertNotIn(
            "str(item_row.get('Description', ''))[:45]",
            self.preview_source,
        )

    def test_common_unicode_punctuation_is_normalized(self):
        for unsafe_character in ("–", "—", "‑", "’", "‘", "“", "”", "…", "•"):
            self.assertIn(f'"{unsafe_character}":', self.preview_source)
        self.assertIn('encode(\n                        "latin-1"', self.preview_source)
        self.assertIn('errors="replace"', self.preview_source)


if __name__ == "__main__":
    unittest.main()
