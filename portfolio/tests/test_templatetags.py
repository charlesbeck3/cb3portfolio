from decimal import Decimal

from django.test import TestCase

from portfolio.templatetags.portfolio_extras import (
    accounting_amount,
    accounting_number,
    accounting_percent,
    get_item,
    percentage_of,
    subtract,
)


class PortfolioExtrasTests(TestCase):
    def test_get_item(self) -> None:
        data = {'a': 1, 'b': 2}
        self.assertEqual(get_item(data, 'a'), 1)
        self.assertIsNone(get_item(data, 'c'))
        self.assertIsNone(get_item(None, 'a'))

    def test_percentage_of(self) -> None:
        self.assertEqual(percentage_of(10, 100), Decimal('10'))
        self.assertEqual(percentage_of(Decimal('5'), Decimal('20')), Decimal('25'))
        # Zero division
        self.assertEqual(percentage_of(10, 0), Decimal('0'))
        # Invalid input
        self.assertEqual(percentage_of('invalid', 100), Decimal('0'))

    def test_subtract(self) -> None:
        self.assertEqual(subtract(10, 4), Decimal('6'))
        self.assertEqual(subtract(Decimal('5.5'), Decimal('2.5')), Decimal('3.0'))
        # Invalid
        self.assertEqual(subtract('invalid', 10), Decimal('0'))

    def test_accounting_amount(self) -> None:
        self.assertIn('1,234', accounting_amount(1234))
        self.assertIn('visibility: hidden', accounting_amount(1234))
        self.assertIn('1,234.00', accounting_amount(1234, 2))
        self.assertEqual(accounting_amount(-1234), '($1,234)')
        self.assertEqual(accounting_amount(-1234.56, 2), '($1,234.56)')
        # Invalid
        self.assertEqual(accounting_amount('invalid'), '-')

    def test_accounting_percent(self) -> None:
        self.assertIn('12.5%', accounting_percent(12.5))
        self.assertIn('visibility: hidden', accounting_percent(12.5))
        self.assertIn('12.50%', accounting_percent(12.5, 2))
        self.assertEqual(accounting_percent(-12.5), '(12.5%)')
        # Invalid
        self.assertEqual(accounting_percent('invalid'), '-')

    def test_accounting_number(self) -> None:
        self.assertIn('1,234.56', accounting_number(1234.56))
        self.assertIn('visibility: hidden', accounting_number(1234.56))
        self.assertEqual(accounting_number(-1234.56), '(1,234.56)')
        # Invalid
        self.assertEqual(accounting_number('invalid'), '-')
