from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # WebSocket for chat room
    re_path(r'^ws/chat/(?P<room_id>[^/]+)/$', consumers.ChatConsumer.as_asgi()),

    # WebSocket for admin notifications
    re_path(r'^ws/notifications/admin/(?P<admin_id>[0-9a-fA-F\-]+)/$', consumers.NotificationConsumer.as_asgi()),
]
