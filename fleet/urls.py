from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PlaneViewSet, PilotViewSet, CommandViewSet

# DRF Router ile otomatik URL oluşturma
router = DefaultRouter()
router.register(r'planes', PlaneViewSet)
router.register(r'pilots', PilotViewSet)
router.register(r'commands', CommandViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
] 