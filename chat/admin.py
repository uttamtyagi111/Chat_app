# from django.contrib import admin
# from .models import ChatRoom, Message

# # @admin.register(ChatRoom)
# class ChatRoomAdmin(admin.ModelAdmin):
#     list_display = ['room_id', 'created_at', 'assigned_agent', 'is_active']


# class MessageAdmin(admin.ModelAdmin):
#     list_display = ('room', 'user', 'content', 'timestamp')
#     search_fields = ('room__name', 'user__username', 'content')
#     list_filter = ('room', 'user')
#     ordering = ('timestamp',)


# admin.site.register(ChatRoom, ChatRoomAdmin)
# admin.site.register(Message, MessageAdmin)
