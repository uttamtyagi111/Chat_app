from django.urls import path
from . import views

urlpatterns = [
    path('tickets/', views.ticket_list, name='ticket-list'),
    path('tickets/add/', views.add_ticket, name='add-ticket'),
    path('tickets/edit/<str:ticket_id>/', views.edit_ticket, name='edit-ticket'),
    path('tickets/delete/<str:ticket_id>/', views.delete_ticket, name='delete-ticket'),
    path('shortcuts/', views.shortcut_list, name='shortcut-list'),
    path('shortcut/<str:shortcut_id>/', views.shortcut_detail, name='shortcut-detail'),
    path('shortcut/add/', views.add_shortcut, name='add-shortcut'),
    path('shortcut/edit/<str:shortcut_id>/', views.edit_shortcut, name='edit-shortcut'),
    path('shortcut/delete/<str:shortcut_id>/', views.delete_shortcut, name='delete-shortcut'),
    path('tags/', views.tag_list, name='tag-list'),
    path('tag/add/', views.add_tag, name='add-tag'),
    path('tag/<str:tag_id>/', views.tag_detail, name='tag-detail'),
    path('tag/edit/<str:tag_id>/', views.edit_tag, name='edit-tag'),
    path('tag/delete/<str:tag_id>/', views.delete_tag, name='delete-tag'),
    # path('triggers/', views.get_active_triggers, name='get-triggers'),
    path('triggers/', views.get_triggers_api, name='trigger-list'),
    path('triggers/add/', views.add_trigger, name='add-trigger'),
    path('test-trigger/', views.trigger_test_view, name='test-trigger'),
    path('update-predefined/', views.update_predefined_messages, name='update_predefined_messages'),

    # path('check-triggers/', views.check_triggers, name='check-triggers'),

    # path('triggers/edit/<str:trigger_id>/', views.edit_trigger, name='edit-trigger'),
    # path('triggers/delete/<str:trigger_id>/', views.delete_trigger, name='delete-trigger'),
    # path('triggers/test/<str:trigger_id>/', views.test_trigger, name='test-trigger'),
]
