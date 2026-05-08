from decimal import Decimal

from django.core.management.base import BaseCommand

from finance.models import OverBudgetAction, OverBudgetPolicy, PaymentMethod, ReceiptPolicy


class Command(BaseCommand):
    help = "Seed baseline V0.5 finance and receipt policies."

    def handle(self, *args, **options):
        over_budget_defaults = [
            {
                "policy_code": "OB-WARN-0-50",
                "policy_name": "Over budget warning up to 50",
                "over_amount_from": Decimal("0.01"),
                "over_amount_to": Decimal("50.00"),
                "action": OverBudgetAction.WARNING,
                "priority": 10,
            },
            {
                "policy_code": "OB-REV-50-250",
                "policy_name": "Over budget review from 50 to 250",
                "over_amount_from": Decimal("50.01"),
                "over_amount_to": Decimal("250.00"),
                "action": OverBudgetAction.REVIEW,
                "priority": 20,
            },
            {
                "policy_code": "OB-AMD-250-750",
                "policy_name": "Over budget amendment from 250 to 750",
                "over_amount_from": Decimal("250.01"),
                "over_amount_to": Decimal("750.00"),
                "action": OverBudgetAction.AMENDMENT_REQUIRED,
                "priority": 30,
            },
            {
                "policy_code": "OB-BLOCK-750",
                "policy_name": "Over budget block above 750",
                "over_amount_from": Decimal("750.01"),
                "action": OverBudgetAction.BLOCK,
                "priority": 40,
            },
        ]
        for data in over_budget_defaults:
            OverBudgetPolicy.objects.update_or_create(policy_code=data["policy_code"], defaults=data)

        receipt_defaults = [
            {
                "policy_code": "RCPT-OPT-LOW",
                "policy_name": "Receipt optional below 25",
                "amount_from": Decimal("0.00"),
                "amount_to": Decimal("24.99"),
                "requires_receipt": False,
                "requires_invoice": False,
                "priority": 10,
            },
            {
                "policy_code": "RCPT-REQ-25",
                "policy_name": "Receipt required from 25",
                "amount_from": Decimal("25.00"),
                "amount_to": Decimal("499.99"),
                "requires_receipt": True,
                "requires_invoice": False,
                "priority": 20,
            },
            {
                "policy_code": "RCPT-INV-500",
                "policy_name": "Invoice required from 500",
                "amount_from": Decimal("500.00"),
                "requires_receipt": True,
                "requires_invoice": True,
                "priority": 30,
            },
            {
                "policy_code": "RCPT-CARD",
                "policy_name": "Company card receipt required",
                "payment_method": PaymentMethod.COMPANY_CARD,
                "amount_from": Decimal("0.01"),
                "requires_receipt": True,
                "requires_invoice": False,
                "priority": 5,
            },
        ]
        for data in receipt_defaults:
            ReceiptPolicy.objects.update_or_create(policy_code=data["policy_code"], defaults=data)

        self.stdout.write(self.style.SUCCESS("V0.5 finance defaults seeded."))
