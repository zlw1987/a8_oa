from django import forms


class ApprovalTaskHistoryFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Keyword")
    request_type = forms.ChoiceField(required=False, label="Request Type")
    outcome_status = forms.ChoiceField(required=False, label="Outcome Status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["request_type"].choices = [
            ("", "All"),
            ("PURCHASE", "Purchase"),
            ("TRAVEL", "Travel"),
        ]

        self.fields["outcome_status"].choices = [
            ("", "All"),
            ("APPROVED", "Approved"),
            ("RETURNED", "Returned"),
            ("REJECTED", "Rejected"),
            ("CANCELLED", "Cancelled"),
        ]

class ApprovalTaskListFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Keyword")
    request_type = forms.ChoiceField(required=False, label="Request Type")
    requester = forms.ChoiceField(required=False, label="Requester")
    due_state = forms.ChoiceField(required=False, label="Due State")

    def __init__(self, *args, requester_choices=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["request_type"].choices = [
            ("", "All"),
            ("PURCHASE", "Purchase"),
            ("TRAVEL", "Travel"),
        ]
        self.fields["due_state"].choices = [
            ("", "All"),
            ("overdue", "Overdue"),
            ("on_time", "On Time"),
            ("no_due_date", "No Due Date"),
        ]

        self.fields["requester"].choices = [("", "All")] + list(requester_choices or [])