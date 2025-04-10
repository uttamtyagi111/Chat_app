from django.db import models
from django.contrib.auth.models import User
import uuid

from django.db import models
from utils.random_id import generate_room_id

class ChatRoom(models.Model):
    room_id = models.CharField(
        max_length=255,
        unique=True,
        default=generate_room_id,
        editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    assigned_agent = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)


    def __str__(self):
        return f"Room {self.room_id} - Agent: {self.assigned_agent or 'Unassigned'}"


from django.db import models

class Message(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    content = models.TextField(blank=True)  # Allow blank for file-only messages
    file_url = models.TextField(blank=True, null=True)  # Store S3 URL
    file_name = models.CharField(max_length=255, blank=True, null=True)  # Original file name
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} - {self.content[:20] if self.content else self.file_name or "No content"}'