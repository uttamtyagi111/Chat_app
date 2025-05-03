from django.urls import path
from chat import views
from django.conf import settings
from django.conf.urls.static import static
from chat.views import UploadFileAPIView,ActiveRoomsAPIView, ChatMessagesByDateAPIView,ChatMessagesAPIView,UserChatAPIView

urlpatterns = [
    path('', views.chat_view, name='chat_home'),
    path('chatroom/', views.chat_view, name='chat_view'),
    path('test-widget/', views.test_widget_view, name='test_widget'),
    path('create-widget/', views.create_widget, name='widget_view'),
    path('direct-chat/<str:widget_id>/', views.direct_chat, name='direct_chat'),
    path('user-chat/', UserChatAPIView.as_view(), name='user_chat'),
    path('agent-chat/<str:room_id>/', views.agent_chat, name='agent_chat'),
    path('websocket-documentation/', views.websocket_documentation, name='websocket_documentation'),
    path('user-chat/upload-file/', UploadFileAPIView.as_view(), name='upload_file'),
    path('agent-chat/<str:room_id>/upload-file/', UploadFileAPIView.as_view(), name='upload_file'),
    path('active-rooms/', ActiveRoomsAPIView.as_view(), name='active-rooms'),
    path('messages-by-date/', ChatMessagesByDateAPIView.as_view(), name='chat-messages-by-date'),
    path('messages/<str:room_id>/', ChatMessagesAPIView.as_view(), name='chat-messages'),
    path('rooms/<str:room_id>/notes/create/', views.create_agent_note, name='create_agent_note'),
    path('rooms/<str:room_id>/notes/', views.get_agent_notes, name='get_agent_notes'),
    path('rooms/<str:room_id>/notes/<str:note_id>/', views.get_note_by_id, name='get_note_by_id'),
    path('rooms/<str:room_id>/notes/<str:note_id>/update/', views.update_agent_note, name='update_agent_note'),
    path('rooms/<str:room_id>/notes/<str:note_id>/delete/', views.delete_agent_note, name='delete_agent_note'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)  