from django import forms
from .models import Conversation

class PromptForm(forms.ModelForm):
    class Meta: 
        model = Conversation
        fields = ['query']
        widgets  = {
            'query': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'query ai',
            }),
        }



