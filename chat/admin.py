from django.contrib import admin
from .models import ChatRoom, Message

class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at')
    search_fields = ('name', 'created_by__username')
    ordering = ('created_at',)

class MessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'user', 'content', 'timestamp')
    search_fields = ('room__name', 'user__username', 'content')
    list_filter = ('room', 'user')
    ordering = ('timestamp',)


admin.site.register(ChatRoom, ChatRoomAdmin)
admin.site.register(Message, MessageAdmin)
