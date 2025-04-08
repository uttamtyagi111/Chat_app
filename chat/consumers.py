# import json
# from datetime import datetime
# from channels.generic.websocket import AsyncWebsocketConsumer
# from utils.redis_client import redis_client


# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_name = self.scope['url_route']['kwargs']['room_id']
#         self.room_group_name = f'chat_{self.room_name}'

#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()

#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

#     # Inside your WebSocket consumer
#     async def receive(self, text_data):
#         data = json.loads(text_data)

#         if data.get('typing') is not None:
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'typing_status',
#                     'typing': data['typing'],
#                     'sender': data['sender']
#                 }
#             )
#         elif data.get('message'):
#             # handle regular message
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'chat_message',
#                     'message': data['message'],
#                     'sender': data['sender']
#                 }
#             )

#     async def typing_status(self, event):
#         await self.send(text_data=json.dumps({
#             'typing': event['typing'],
#             'sender': event['sender']
#         }))

#     async def chat_message(self, event):
#         await self.send(text_data=json.dumps({
#             'message': event['message'],
#             'sender': event['sender']
#         }))
import json
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer
from utils.redis_client import redis_client
from datetime import datetime

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
        # ✅ Typing indicator
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

        # ✅ Seen Status - Single Message
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

        # ✅ Sending new message
        if data.get('message'):
            message_id = data.get("message_id") or str(uuid.uuid4())
            timestamp = datetime.utcnow().isoformat()
            sender = data.get('sender')
            message = data.get('message')

            redis_client.hset(f'message:{message_id}', mapping={
                "sender": sender,
                "message": message,
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
                    'timestamp': timestamp
                }
            )

    async def typing_status(self, event):
        await self.send(text_data=json.dumps({
            'typing': event['typing'],
            'sender': event['sender']
        }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'message_id': event['message_id'],
            'timestamp': event['timestamp'],
            'status': 'delivered'
        }))

    async def message_seen(self, event):
        await self.send(text_data=json.dumps({
            'message_id': event['message_id'],
            'status': 'seen',
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))
