from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .forms import DocumentForm
from .models import Document, ProjectOp
from .utils import sha256_file

def home(request):
    return render(request, "core/home.html", {
        "projects": ProjectOp.objects.all()[:10],
        "docs": Document.objects.order_by("-created_at")[:10],
    })

@login_required
@require_http_methods(["GET","POST"])
def upload_doc(request):
    if request.method == "POST":
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.created_by = request.user
            if doc.file:
                doc.checksum_sha256 = sha256_file(doc.file)
            # de-dupe exact files by checksum (basic PoC)
            if Document.objects.filter(checksum_sha256=doc.checksum_sha256).exists():
                return render(request, "core/upload.html", {"form": form, "docs": Document.objects.all()[:20], "error": "Duplicate file detected (checksum match)."})
            doc.save()
            form.save_m2m()
            return redirect("upload")
    else:
        form = DocumentForm()
    return render(request, "core/upload.html", {"form": form, "docs": Document.objects.order_by("-created_at")[:20]})
