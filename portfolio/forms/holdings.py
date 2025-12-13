from django import forms
from django.core.exceptions import ValidationError

from portfolio.models import Security


class AddHoldingForm(forms.Form):
    security_id = forms.IntegerField(widget=forms.HiddenInput())
    initial_shares = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        required=True,
    )

    def clean_security_id(self) -> int:
        security_id = self.cleaned_data["security_id"]
        if not Security.objects.filter(id=security_id).exists():
            raise ValidationError("Security not found.")
        return security_id
