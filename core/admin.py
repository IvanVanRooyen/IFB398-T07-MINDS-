# core/admin.py
from django.contrib import admin as djadmin
from django.contrib.gis.admin import GISModelAdmin

from .models import ProjectOp, Document

@djadmin.register(ProjectOp)
class ProjectOpAdmin(GISModelAdmin):
    list_display = ("name", "mode", "commodity")

@djadmin.register(Document)
class DocumentAdmin(djadmin.ModelAdmin):  # Document doesn’t need a map in admin
    list_display = ("title", "year", "doc_type", "confidentiality", "project")