from django.urls import path
from .views import home, profile #,upload_doc

urlpatterns = [
    path("", home, name="home"),
    # path("upload/", upload_doc, name="upload"),
    path("profile/", profile, name="profile"),
]
