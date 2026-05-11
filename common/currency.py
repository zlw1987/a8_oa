from decimal import Decimal, ROUND_HALF_UP


COMPANY_BASE_CURRENCY = "USD"
BASE_CURRENCY_DECIMAL_PLACES = Decimal("0.01")
EXCHANGE_RATE_DECIMAL_PLACES = Decimal("0.00000001")


def quantize_money(value):
    return (value or Decimal("0.00")).quantize(BASE_CURRENCY_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def quantize_rate(value):
    return (value or Decimal("0.00000000")).quantize(EXCHANGE_RATE_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
