import json
from channels.generic.websocket import AsyncWebsocketConsumer
from utils.redis_client import redis_client
from datetime import datetime
from asgiref.sync import sync_to_async

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        from chat.models import ChatRoom
        self.room_name = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_name}'
        print("Connecting:", self.scope['user'], "to room:", self.room_group_name)
        await self.set_room_active_status(self.room_name, True)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        from chat.models import ChatRoom
        print("Disconnecting:", self.scope['user'])
        await self.set_room_active_status(self.room_name, False)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        print("Received on server:", data)

        if 'typing' in data and 'content' in data and data.get('sender') != 'agent':
            print("Broadcasting typing to group:", self.room_group_name, data)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_status',
                    'typing': data['typing'],
                    'content': data['content'],
                    'sender': data['sender']
                }
            )
            return

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

        from utils.random_id import generate_id
        
        if data.get('message') or data.get('file_url'):
            message_id = data.get("message_id") or generate_id()
            timestamp = datetime.utcnow().isoformat()
            sender = data.get('sender', 'User')
            message = data.get('message', '')
            file_url = data.get('file_url')
            file_name = data.get('file_name')

            redis_client.hset(f'message:{message_id}', mapping={
                "sender": sender,
                "message": message,
                "file_url": file_url or "",
                "file_name": file_name or "",
                "delivered": "true",
                "seen": "false",
                "timestamp": timestamp
            })

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
        print("Sending chat message to client:", event)
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
        print("Sending typing to client:", self.scope['user'], event)
        await self.send(text_data=json.dumps({
            'typing': event['typing'],
            'content': event.get('content', ''),
            'sender': event['sender']
        }))

    async def message_seen(self, event):
        print("Sending seen status to client:", event)
        await self.send(text_data=json.dumps({
            'message_id': event['message_id'],
            'status': 'seen',
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))
        
    @sync_to_async
    def set_room_active_status(self, room_id, status: bool):
        from chat.models import ChatRoom
        try:
            room = ChatRoom.objects.get(room_id=room_id)
            room.is_active = status
            room.save()
        except ChatRoom.DoesNotExist:
            pass