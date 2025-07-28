from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<room_id>[^/]+)/$', consumers.ChatConsumer.as_asgi()),
    
    # Agent dashboard connection
    re_path(r'ws/notifications/agent/(?P<agent_id>\w+)/$', consumers.NotificationConsumer.as_asgi()),
]
