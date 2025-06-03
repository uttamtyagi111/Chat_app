from django.urls import path
from . import views
from .views import ContactListCreateView, ContactRetrieveUpdateDeleteView,AssignAgentToRoom, DeactivateRoom, AgentAnalytics, ExportChatHistoryAPIView
from .views import AddAgentView,EditAgentAPIView,DeleteAgentAPIView,AgentDetailAPIView,AgentFeedbackList

urlpatterns = [
    # Agent URLs
    path('agents/', views.agent_list, name='agent-list'),
    path('agents/add/', AddAgentView.as_view(), name='add-agent'),
    path('agents/<str:agent_id>/edit/', EditAgentAPIView.as_view(), name='edit-agent'),
    path('agents/<str:agent_id>/delete/', DeleteAgentAPIView.as_view(), name='delete-agent'),
    path('agent/<str:agent_id>/', AgentDetailAPIView.as_view(), name='agent-detail'),
    path('assign-agent/', AssignAgentToRoom.as_view(), name='assign-agent'),
    path('deactivate-room/', DeactivateRoom.as_view(), name='deactivate-room'),
    # Agent Analytics URLs
    path('agent-analytics/<str:agent_name>/', AgentAnalytics.as_view(), name='agent-analytics'),
    # Export Chat History URL
    path('export-chat-history/', ExportChatHistoryAPIView.as_view(), name='export-chat-history'),
    
    # User Feedback URL
    path('user-feedback/', views.user_feedback, name='user-feedback'),
    path('agent-feedback/<str:agent_name>/', AgentFeedbackList.as_view(), name='agent-feedback'),

    # # Global Conversation URLs
    path('conversations/', views.conversation_list, name='conversation-list'),
    path('conversations/<str:room_id>/', views.chat_room_view, name='chat_room_view'),

    # Contact URLs
    path('contacts/', ContactListCreateView.as_view(), name='contact-list-create'),
    path('contact/<str:pk>/', ContactRetrieveUpdateDeleteView.as_view(), name='contact-detail'),
]
