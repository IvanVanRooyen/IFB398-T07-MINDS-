from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from config import settings


def health(_):
    return HttpResponse("ok")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("health/", health),
]


if settings.DEBUG:
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
