import json
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer
from utils.redis_client import redis_client
from datetime import datetime
from asgiref.sync import sync_to_async
# from chat.models import Message, ChatRoom

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_name}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        print("Received on server:", data)

        # Typing indicator
        if data.get('typing') is not None:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_status',
                    'typing': data['typing'],
                    'sender': data['sender']
                }
            )
            return

        # Seen status
        if data.get('status') == 'seen' and data.get('message_id'):
            message_id = data['message_id']
            sender = data.get('sender', 'unknown')
            timestamp = datetime.utcnow().isoformat()

            redis_client.hset(f'message:{message_id}', mapping={
                "seen": "true",
                "seen_at": timestamp
            })

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_seen',
                    'message_id': message_id,
                    'sender': sender,
                    'timestamp': timestamp
                }
            )
            return

        # Sending new message (text or file URL)
        if data.get('message') or data.get('file_url'):
            message_id = data.get("message_id") or str(uuid.uuid4())
            timestamp = datetime.utcnow().isoformat()
            sender = data.get('sender', 'User')
            message = data.get('message', '')
            file_url = data.get('file_url')
            file_name = data.get('file_name')

            # # Save to database
            # room = await sync_to_async(ChatRoom.objects.get)(id=self.room_name)
            # user = self.scope['user'] if self.scope['user'].is_authenticated else None
            # await sync_to_async(Message.objects.create)(
            #     room=room,
            #     user=user,
            #     content=message,
            #     file_url=file_url,
            #     file_name=file_name
            # )

            # Store in Redis
            redis_client.hset(f'message:{message_id}', mapping={
                "sender": sender,
                "message": message,
                "file_url": file_url or "",
                "file_name": file_name or "",
                "delivered": "true",
                "seen": "false",
                "timestamp": timestamp
            })

            # Broadcast to group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': sender,
                    'message_id': message_id,
                    'file_url': file_url,
                    'file_name': file_name,
                    'timestamp': timestamp
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'message_id': event['message_id'],
            'file_url': event['file_url'],
            'file_name': event['file_name'],
            'timestamp': event['timestamp'],
            'status': 'delivered'
        }))

    async def typing_status(self, event):
        await self.send(text_data=json.dumps({
            'typing': event['typing'],
            'sender': event['sender']
        }))

    async def message_seen(self, event):
        await self.send(text_data=json.dumps({
            'message_id': event['message_id'],
            'status': 'seen',
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))