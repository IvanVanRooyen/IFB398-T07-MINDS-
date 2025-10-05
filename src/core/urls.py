from django.urls import path
from .views import home, upload_doc

urlpatterns = [
    path("", home, name="home"),
    path("upload/", upload_doc, name="upload"),
]
