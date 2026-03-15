from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("home/", views.home, name="home"),
    path("prospects/", views.prospects, name="prospects"),
    path("drillholes/", views.drillholes, name="drillholes"),
    path("tenements/", views.tenements, name="tenements"),
    path("documents/", views.documents, name="documents"),
    path("documents/<uuid:pk>/", views.document_detail, name="document_detail"),
    path("documents/<uuid:pk>/delete/", views.delete_document, name="delete_document"),
    path("map/", views.map_view, name="map_view"),
    path("ai-insights/", views.ai_insights, name="ai_insights"),

    path("upload/", views.upload_doc, name="upload"),
    path("ai/report/<uuid:process_id>/", views.project_report, name="project_report"),

    # GeoJSON API endpoints for the map viewer
    path("api/geojson/projects/", views.geojson_projects, name="geojson_projects"),
    path("api/geojson/tenements/", views.geojson_tenements, name="geojson_tenements"),
    path("api/geojson/prospects/", views.geojson_prospects, name="geojson_prospects"),
    path("api/geojson/drillholes/", views.geojson_drillholes, name="geojson_drillholes"),
]
