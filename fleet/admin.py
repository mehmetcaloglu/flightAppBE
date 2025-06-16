from django.contrib import admin
from django.contrib.gis import admin as gis_admin
from .models import Plane, Pilot, Command


@admin.register(Pilot)
class PilotAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name']


@admin.register(Plane)
class PlaneAdmin(gis_admin.GISModelAdmin):
    list_display = ['name', 'pilot', 'created_at', 'updated_at']
    list_filter = ['created_at']
    search_fields = ['name', 'pilot__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    list_display = ['plane', 'status', 'message', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['plane__name', 'message']
    readonly_fields = ['created_at', 'updated_at']
