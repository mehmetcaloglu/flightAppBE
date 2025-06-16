from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/planes/positions/?$', consumers.PlanePositionsConsumer.as_asgi()),
    re_path(r'ws/pilot/commands/?$', consumers.PilotCommandConsumer.as_asgi()),
    re_path(r'ws/commands/status/?$', consumers.CommandStatusConsumer.as_asgi()),
] 