from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def health(_): return HttpResponse("ok")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("health/", health),
]
