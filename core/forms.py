from django import forms
from django.forms import ModelForm
from .models import Document
from .tagging import TAG_CHOICES

class DocumentForm(ModelForm):
    timestamp = forms.DateField(
        required=False,
        input_formats=[
            "%Y-%m-%d",   # 2025-10-12  (default, ISO)
            "%d/%m/%Y",   # 12/10/2025
            "%d-%m-%Y",   # 12-10-2025
        ],
        widget=forms.DateInput(attrs={"type": "date"}), # HTML5 picker
        label="Date"
    )
    
    tags = forms.TypedMultipleChoiceField(
        choices=TAG_CHOICES,
        coerce=int,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Tags",
    )

    class Meta:
        model = Document
        fields = [
            "title", "file", "organisation", "process",
            "timestamp", "doc_type", "confidentiality", "tags",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["tags"] = self.instance.tags or []

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.tags = list(map(int, self.cleaned_data.get("tags", [])))
        if commit:
            obj.save()
        return obj