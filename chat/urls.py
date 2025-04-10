from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # path('', views.index, name='index'),
    # path('<str:room_name>/', views.room, name='room'),
    path('', views.chat_view, name='chat_home'),
    path('chatroom/', views.chat_view, name='chat_view'),
    path('user-chat/', views.user_chat, name='user_chat'),
    path('agent-dashboard/', views.agent_dashboard, name='agent_dashboard'),
    path('agent-chat/<uuid:room_id>/', views.agent_chat, name='agent_chat'),
    path('user-chat/upload-file/', views.UploadFileAPIView.as_view(), name='upload_file'),
    path('agent-chat/<uuid:room_id>/upload-file/', views.UploadFileAPIView.as_view(), name='upload_file'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)