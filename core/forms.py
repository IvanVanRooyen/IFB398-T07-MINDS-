from django import forms
from .models import Document

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        # fields = ["file","title","year","doc_type","confidentiality","project"]
        fields = ["file"]
