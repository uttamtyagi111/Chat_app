import json
from channels.generic.websocket import AsyncWebsocketConsumer
from wish_bot.db import (
    get_chat_collection,
    get_room_collection,
    insert_with_timestamps,
    update_with_timestamp,
)
from utils.redis_client import redis_client
from datetime import datetime
from asgiref.sync import sync_to_async
from utils.random_id import generate_id


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = 'anonymous'  # Fixed user identity
        self.room_name = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_name}'
        
        # Check if this connection is from an agent
        query_string = self.scope.get('query_string', b'').decode()
        self.is_agent = 'agent=true' in query_string
        
        print(f"[CONNECT] {self.user} joined {self.room_group_name}, is_agent: {self.is_agent}")
        await self.set_room_active_status(self.room_name, True)

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Initialize predefined messages state in Redis only for non-agent connections
        if not self.is_agent:
            self.predefined_messages = [
                "Welcome to the chat room!",
                "Great to see you! What's on your mind?",
                "Keep the conversation going!"
            ]
            redis_key = f"predefined:{self.room_name}:{self.user}"
            redis_client.set(redis_key, 0)  # Start with index 0

            # Send the first predefined message
            await self.send_predefined_message(0)
        else:
            await self.send_chat_history()
            
    async def send_chat_history(self):
        collection = await sync_to_async(get_chat_collection)()
        
        # Fetch messages for this room, sorted by timestamp
        messages = await sync_to_async(lambda: list(
            collection.find(
                {'room_id': self.room_name},
                {'_id': 0}  # Exclude MongoDB _id field
            ).sort('timestamp', 1)  # Sort by timestamp ascending
        ))()
        
        print(f"[HISTORY] Sending {len(messages)} messages to agent for room {self.room_name}")
        
        # Send each message to the agent
        for msg in messages:
            # Convert datetime to string for JSON serialization
            if isinstance(msg.get('timestamp'), datetime):
                msg['timestamp'] = msg['timestamp'].isoformat()
            
            # Send historical message
            await self.send(text_data=json.dumps({
                'message': msg.get('message', ''),
                'sender': msg.get('sender', 'unknown'),
                'message_id': msg.get('message_id', ''),
                'file_url': msg.get('file_url', ''),
                'file_name': msg.get('file_name', ''),
                'timestamp': msg.get('timestamp', ''),
                'status': 'history'  # Mark as historical message
            }))
            
            
    async def disconnect(self, close_code):
        print(f"[DISCONNECT] {self.user} leaving {self.room_group_name}")
        if hasattr(self, 'room_name'):
            await self.set_room_active_status(self.room_name, False)
            redis_client.delete(f'typing:{self.room_name}:{self.user}')
            redis_client.delete(f'predefined:{self.room_name}:{self.user}')
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        print(f"[RECEIVED] {data}")
        collection = await sync_to_async(get_chat_collection)()

        # Handle Typing Status
        if data.get('typing') is not None and 'content' in data and data.get('sender') != 'agent':
            await self.handle_typing(data)
            return

        # Handle Seen Message Status
        if data.get('status') == 'seen' and data.get('message_id'):
            await self.handle_seen_status(data, collection)
            return

        # Handle Sending Chat Message
        if data.get('message') or data.get('file_url'):
            await self.handle_new_message(data, collection)

    async def handle_typing(self, data):
        typing_key = f'typing:{self.room_name}:{data["sender"]}'
        if data['typing']:
            redis_client.setex(typing_key, 10, json.dumps({
                'typing': data['typing'],
                'content': data['content'],
                'sender': data['sender']
            }))
        else:
            redis_client.delete(typing_key)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_status',
                'typing': data['typing'],
                'content': data['content'],
                'sender': data['sender']
            }
        )

    async def handle_seen_status(self, data, collection):
        message_id = data['message_id']
        sender = data.get('sender', self.user)
        timestamp = datetime.utcnow()

        print(f"[SEEN STATUS] Marking message '{message_id}' as seen by '{sender}' at {timestamp}")

        result = await sync_to_async(update_with_timestamp)(
            collection,
            {'message_id': message_id},
            {'$set': {
                'seen': True,
                'seen_at': timestamp
            }}
        )

        if result.modified_count > 0:
            print(f"[DB ✅] Seen status updated for message_id: {message_id}")
        else:
            print(f"[DB ❌] No document found to update for message_id: {message_id}")

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'message_seen',
                'message_id': message_id,
                'sender': sender,
                'timestamp': timestamp.isoformat()
            }
        )

    async def handle_new_message(self, data, collection):
        message_id = data.get('message_id') or generate_id()
        timestamp = datetime.utcnow()
        sender = data.get('sender', self.user)
        message = data.get('message', '')
        file_url = data.get('file_url', '')
        file_name = data.get('file_name', '')

        doc = {
            'message_id': message_id,
            'room_id': self.room_name,
            'sender': sender,
            'message': message,
            'file_url': file_url,
            'file_name': file_name,
            'delivered': True,
            'seen': False,
            'timestamp': timestamp
        }

        insert_result = await sync_to_async(insert_with_timestamps)(collection, doc)

        if insert_result.inserted_id:
            print(f"[DB ✅] Message inserted with ID: {insert_result.inserted_id}")
        else:
            print(f"[DB ❌] Message insert failed for: {message_id}")

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': sender,
                'message_id': message_id,
                'file_url': file_url,
                'file_name': file_name,
                'timestamp': timestamp.isoformat()
            }
        )

        # Check and send next predefined message only if sender is not 'agent'
        if sender != 'agent' and not self.is_agent:
            redis_key = f"predefined:{self.room_name}:{self.user}"
            current_index = int(redis_client.get(redis_key) or 0)
            next_index = current_index + 1
            if next_index < len(self.predefined_messages):
                redis_client.set(redis_key, next_index)
                await self.send_predefined_message(next_index)

    async def send_predefined_message(self, index):
        # Only proceed if this is not an agent connection
        if hasattr(self, 'is_agent') and self.is_agent:
            return
            
        collection = await sync_to_async(get_chat_collection)()
        message = self.predefined_messages[index]
        message_id = generate_id()
        timestamp = datetime.utcnow()

        doc = {
            'message_id': message_id,
            'room_id': self.room_name,
            'sender': 'System',
            'message': message,
            'file_url': '',
            'file_name': '',
            'delivered': True,
            'seen': False,
            'timestamp': timestamp
        }

        insert_result = await sync_to_async(insert_with_timestamps)(collection, doc)
        if insert_result.inserted_id:
            print(f"[DB ✅] Predefined message inserted with ID: {insert_result.inserted_id}")
        else:
            print(f"[DB ❌] Predefined message insert failed for: {message_id}")

        # Send predefined message only to the user's WebSocket connection
        await self.send(text_data=json.dumps({
            'message': message,
            'sender': 'System',
            'message_id': message_id,
            'file_url': '',
            'file_name': '',
            'timestamp': timestamp.isoformat(),
            'status': 'delivered'
        }))

    async def chat_message(self, event):
        print(f"[SEND MESSAGE] {event}")
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
        print(f"[SEND TYPING] {event}")
        await self.send(text_data=json.dumps({
            'typing': event['typing'],
            'content': event.get('content', ''),
            'sender': event['sender']
        }))

    async def message_seen(self, event):
        print(f"[SEND SEEN STATUS] {event}")
        await self.send(text_data=json.dumps({
            'message_id': event['message_id'],
            'status': 'seen',
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))

    @sync_to_async
    def set_room_active_status(self, room_id, status: bool):
        collection = get_room_collection()
        try:
            collection.update_one(
                {'room_id': room_id},
                {'$set': {'is_active': status}},
                upsert=True
            )
        except Exception as e:
            print(f"[ERROR] Updating room status: {e}")