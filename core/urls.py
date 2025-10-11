from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("prospects/", views.prospects, name="prospects"),
    path("drillholes/", views.drillholes, name="drillholes"),
    path("tenements/", views.tenements, name="tenements"),
    path("documents/", views.documents, name="documents"),
    path("ai-insights/", views.ai_insights, name="ai_insights"),

    path("upload/", views.upload_doc, name="upload"),
    path("ai/report/<uuid:process_id>/", views.project_report, name="project_report"),
]
