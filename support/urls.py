from django.urls import path
from . import views
from .views import PatchTriggerAPIView

urlpatterns = [
    path('tickets/', views.ticket_list, name='ticket-list'),
    path('tickets/add/', views.add_ticket, name='add-ticket'),
    path('tickets/edit/<str:ticket_id>/', views.edit_ticket, name='edit-ticket'),
    path('tickets/delete/<str:ticket_id>/', views.delete_ticket, name='delete-ticket'),

    # Shortcuts
    path('shortcuts/', views.shortcut_list, name='shortcut-list'),
    path('shortcut/add/', views.add_shortcut, name='add-shortcut'),
    path('shortcut/<str:shortcut_id>/', views.shortcut_detail, name='shortcut-detail'),
    path('shortcut/edit/<str:shortcut_id>/', views.edit_shortcut, name='edit-shortcut'),
    path('shortcut/delete/<str:shortcut_id>/', views.delete_shortcut, name='delete-shortcut'),

    # Tags
    path('tags/', views.tag_list, name='tag-list'),
    path('tag/add/', views.add_tag, name='add-tag'),
    path('tag/<str:tag_id>/', views.tag_detail, name='tag-detail'),
    path('tag/edit/<str:tag_id>/', views.edit_tag, name='edit-tag'),
    path('tag/delete/<str:tag_id>/', views.delete_tag, name='delete-tag'),
    path('tags/shortcut/<str:shortcut_id>/', views.tags_by_shortcut_id, name='tags_by_shortcut_id'),
    path('tags/room/<str:room_id>/', views.tags_by_room_id, name='tags_by_room_id'),

    # Triggers
    path('triggers/', views.get_triggers_api, name='trigger-list'),
    path('trigger/<str:trigger_id>/', views.get_trigger_detail, name='trigger-detail'),
    path('triggers/add/', views.add_trigger, name='add-trigger'),
    path('test-trigger/', views.trigger_test_view, name='test-trigger'),
    path('trigger/update/<str:trigger_id>/', PatchTriggerAPIView.as_view(), name='update_trigger_message'),
]
