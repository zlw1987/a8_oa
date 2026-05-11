from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def money(amount, currency="USD"):
    currency_code = currency or "USD"
    if amount in [None, ""]:
        value = Decimal("0.00")
    else:
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            value = Decimal("0.00")
    return f"{currency_code} {value:,.2f}"
