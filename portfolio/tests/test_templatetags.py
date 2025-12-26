from django.test import SimpleTestCase

from portfolio.templatetags.portfolio_tags import currency, percentage, variance_class


class TemplateTagsTests(SimpleTestCase):
    def test_currency_filter(self) -> None:
        """Test currency formatting."""
        self.assertEqual(currency(1234.56), "$1,234.56")
        self.assertEqual(currency("1234.56"), "$1,234.56")
        self.assertEqual(currency(1234), "$1,234.00")
        self.assertEqual(currency(0), "$0.00")
        self.assertEqual(currency("invalid"), "invalid")

    def test_percentage_filter(self) -> None:
        """Test percentage formatting."""
        self.assertEqual(percentage(12.3456), "12.35%")
        self.assertEqual(percentage(12.3456, 1), "12.3%")
        self.assertEqual(percentage("12.34"), "12.34%")
        self.assertEqual(percentage(0), "0.00%")
        self.assertEqual(percentage("invalid"), "invalid")

    def test_variance_class_filter(self) -> None:
        """Test variance CSS class generation."""
        self.assertEqual(variance_class(6), "text-danger")
        self.assertEqual(variance_class(-6), "text-danger")
        self.assertEqual(variance_class(4), "text-success")
        self.assertEqual(variance_class(-4), "text-success")
        self.assertEqual(
            variance_class(5), "text-success"
        )  # Default threshold 5 (inclusive as success)
        self.assertEqual(variance_class(5.1), "text-danger")

        # Test custom threshold
        self.assertEqual(variance_class(2, threshold=1), "text-danger")
        self.assertEqual(variance_class("invalid"), "")
