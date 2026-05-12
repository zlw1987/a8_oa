from approvals.management.commands.send_approval_escalations import Command as SendEscalationsCommand


class Command(SendEscalationsCommand):
    help = "Process overdue approval task escalations. Alias for send_approval_escalations."
