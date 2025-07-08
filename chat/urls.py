from django.urls import path
from chat import views
from django.conf import settings
from django.conf.urls.static import static
from chat.views import UpdateWidgetAPIView, UploadFileAPIView,ActiveRoomsAPIView, ChatMessagesByDateAPIView,ChatMessagesAPIView,UserChatAPIView,RoomListAPIView,RoomDetailAPIView, TestAgentAssignView

urlpatterns = [
    
    
    path('rooms/', RoomListAPIView.as_view(), name='room-list'),
    path('rooms/<str:room_id>/', RoomDetailAPIView.as_view(), name='room-detail'),
    path('active-rooms/', ActiveRoomsAPIView.as_view(), name='active-rooms'),
    # path('agents/',AgentListAPIView.as_view(), name='agents-list'),
    path('chatroom/', views.chat_view, name='chat_view'),
    path('test-widget/', views.test_widget_view, name='test_widget'),
    
    ## Widget Endpoints
    path('create-widget/', views.create_widget, name='widget_view'),
    path('widget/<str:widget_id>/', views.get_widget, name='get_widget'),  # GET: Retrieve a single widget
    path('widgets/', views.get_widget, name='list_widgets'),               # GET: List all widgets
    path('widget/<str:widget_id>/update/', UpdateWidgetAPIView.as_view(), name='update_widget'),  # PUT: Update a widget
    path('widget/<str:widget_id>/delete/', views.delete_widget, name='delete_widget'),  # DELETE: Delete a widget
    path('direct-chat/<str:widget_id>/', views.direct_chat, name='direct_chat'),
    path('user-chat/', UserChatAPIView.as_view(), name='user_chat'),
    path('agent-chat/<str:room_id>/', TestAgentAssignView.as_view(), name='agent_chat'),
    path('websocket-documentation/', views.websocket_documentation, name='websocket_documentation'),
    path('user-chat/upload-file/', UploadFileAPIView.as_view(), name='upload_file'),
    path('agent-chat/<str:room_id>/upload-file/', UploadFileAPIView.as_view(), name='upload_file'),
    
    
    path('messages-by-date/', ChatMessagesByDateAPIView.as_view(), name='chat-messages-by-date'),
    path('messages/<str:room_id>/', ChatMessagesAPIView.as_view(), name='chat-messages'),
    
    ## Agent Notes Endpoints
    path('rooms/<str:room_id>/notes/create/', views.create_agent_note, name='create_agent_note'),
    path('rooms/<str:room_id>/notes/', views.get_agent_notes, name='get_agent_notes'),
    path('rooms/<str:room_id>/notes/<str:note_id>/', views.get_note_by_id, name='get_note_by_id'),
    path('rooms/<str:room_id>/notes/<str:note_id>/update/', views.update_agent_note, name='update_agent_note'),
    path('rooms/<str:room_id>/notes/<str:note_id>/delete/', views.delete_agent_note, name='delete_agent_note'),
    

   ## Public API Endpoints
    path("widget/settings/<str:widget_id>/", views.public_widget_settings, name='public_widget_settings'),
    


     path('test-ip-geolocation/', views.test_ip_geolocation, name='test_ip_geolocation'),

]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)  