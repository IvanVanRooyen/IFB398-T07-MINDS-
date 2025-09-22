from django.http import HttpResponse
from django.shortcuts import render
from ollama import chat

from .forms import PromptForm
from .models import Conversation

DEFAULT_MODEL = "granite3.2-vision"


def search_view(request):
    form = PromptForm()
    messages = Conversation.objects.all()[:10]

    return render(request, "ollama/index.html", {"form": form, "messages": messages})


def send_query(request):
    if request.method == "POST":
        form = PromptForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data["query"]
            try:
                response = chat(
                    model=DEFAULT_MODEL,
                    messages=[
                        {
                            "role": "user",
                            "content": query,
                        },
                    ],
                )
                message = form.save(commit=False)
                message.response = response["message"]["content"]
                message.save()

                return render(request, "ollama/message.html", {"message": message})

            except Exception as e:
                return HttpResponse(f"""
                    <div class="alert" role="alert">
                        Error: {str(e)}         
                    </div>
                """)
    return HttpResponse("<div>invalid request</div>")


def clear_conversations(request):
    if request.method == "POST":
        Conversation.objects.all().delete()
        return HttpResponse('<div class="alert">conversations cleared.</div>')

    return HttpResponse("")
