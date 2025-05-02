import json
import uuid
from datetime import datetime, timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
from wish_bot.db import (
    get_chat_collection,
    get_room_collection,
    insert_with_timestamps,
    update_with_timestamp,
)
from utils.redis_client import redis_client
from asgiref.sync import sync_to_async
from utils.random_id import generate_id


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_name}'
        self.is_agent = 'agent=true' in self.scope.get('query_string', b'').decode()
        self.user = f'user_{str(uuid.uuid4())}' if not self.is_agent else 'agent'

        # Validate room
        room_valid = await sync_to_async(self.validate_room)()
        if not room_valid:
            print(f"[ERROR] Invalid or inactive room: {self.room_name}")
            await self.close()
            return

        print(f"[CONNECT] {self.user} joined {self.room_group_name}, is_agent: {self.is_agent}")
        await self.set_room_active_status(self.room_name, True)

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        if not self.is_agent:
            self.predefined_messages = [
                "Welcome to the chat room!",
                "Please provide your name and email to continue."
            ]
            redis_key = f"predefined:{self.room_name}:{self.user}"
            redis_client.set(redis_key, 0)
            await self.send_predefined_message(0)
        else:
            await self.send_chat_history()

    def validate_room(self):
        room_collection = get_room_collection()
        room = room_collection.find_one({'room_id': self.room_name})
        return room is not None and room.get('is_active', False)

    async def send_chat_history(self):
        collection = await sync_to_async(get_chat_collection)()
        messages = await sync_to_async(lambda: list(
            collection.find(
                {'room_id': self.room_name},
                {'_id': 0}
            ).sort('timestamp', 1)
        ))()

        print(f"[HISTORY] Sending {len(messages)} messages to agent for room {self.room_name}")

        for msg in messages:
            if isinstance(msg.get('timestamp'), datetime):
                msg['timestamp'] = msg['timestamp'].isoformat()
            await self.send(text_data=json.dumps({
                'message': msg.get('message', ''),
                'sender': msg.get('sender', 'unknown'),
                'message_id': msg.get('message_id', ''),
                'file_url': msg.get('file_url', ''),
                'file_name': msg.get('file_name', ''),
                'timestamp': msg.get('timestamp', ''),
                'status': 'history'
            }))

    async def disconnect(self, close_code):
        print(f"[DISCONNECT] {self.user} leaving {self.room_group_name}")
        if hasattr(self, 'room_name'):
            await self.set_room_active_status(self.room_name, False)
            redis_client.delete(f'typing:{self.room_name}:{self.user}')
            redis_client.delete(f'predefined:{self.room_name}:{self.user}')
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            print(f"[RECEIVED] {data}")
            collection = await sync_to_async(get_chat_collection)()

            # Rate limiting for non-agents
            if not self.is_agent and (data.get('message') or data.get('file_url') or data.get('form_data')):
                rate_limit_key = f"rate_limit:{self.user}"
                current_time = datetime.now()
                last_message_time = redis_client.get(rate_limit_key)
                if last_message_time:
                    try:
                        last_message_time = datetime.fromisoformat(last_message_time)  # Remove .decode()
                        if (current_time - last_message_time) < timedelta(seconds=1):
                            await self.send(text_data=json.dumps({
                                'error': 'Rate limit exceeded. Please wait a moment.'
                            }))
                            return
                    except ValueError as e:
                        print(f"[ERROR] Invalid timestamp format in Redis: {e}")
                        # Reset the rate limit key if the timestamp is invalid
                        redis_client.delete(rate_limit_key)
                redis_client.setex(rate_limit_key, 60, current_time.isoformat())

            if data.get('typing') is not None and 'content' in data:
                await self.handle_typing(data)
                return

            if data.get('status') == 'seen' and data.get('message_id'):
                await self.handle_seen_status(data, collection)
                return

            if data.get('form_data'):
                await self.handle_form_data(data, collection)
                return

            if data.get('message') or data.get('file_url'):
                await self.handle_new_message(data, collection)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON: {e}")
            await self.send(text_data=json.dumps({'error': 'Invalid message format'}))

    async def handle_typing(self, data):
        typing_key = f'typing:{self.room_name}:{data["sender"]}'
        try:
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
        except Exception as e:
            print(f"[ERROR] Handling typing: {e}")

    async def handle_seen_status(self, data, collection):
        message_id = data['message_id']
        sender = data.get('sender', self.user)
        timestamp = datetime.utcnow()

        print(f"[SEEN STATUS] Marking message '{message_id}' as seen by '{sender}' at {timestamp}")

        try:
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
        except Exception as e:
            print(f"[ERROR] Updating seen status: {e}")

    async def handle_form_data(self, data, collection):
        form_data = data.get('form_data', {})
        name = form_data.get('name', '')
        email = form_data.get('email', '')
        message_id = generate_id()
        timestamp = datetime.utcnow()
        sender = data.get('sender', self.user)

        formatted_message = f"Name: {name}, Email: {email}"
        doc = {
            'message_id': message_id,
            'room_id': self.room_name,
            'sender': sender,
            'message': formatted_message,
            'file_url': '',
            'file_name': '',
            'delivered': True,
            'seen': False,
            'timestamp': timestamp,
            'user_info': {
                'name': name,
                'email': email
            }
        }

        try:
            insert_result = await sync_to_async(insert_with_timestamps)(collection, doc)
            if insert_result.inserted_id:
                print(f"[DB ✅] User info form data inserted with ID: {insert_result.inserted_id}")
            else:
                print(f"[DB ❌] User info form data insert failed for: {message_id}")

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': formatted_message,
                    'sender': sender,
                    'message_id': message_id,
                    'file_url': '',
                    'file_name': '',
                    'timestamp': timestamp.isoformat(),
                    'form_data_received': True
                }
            )
            await self.send_thank_you_message(name)
        except Exception as e:
            print(f"[ERROR] Handling form data: {e}")
            await self.send(text_data=json.dumps({'error': 'Failed to process form data'}))

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

        try:
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

            if not self.is_agent and sender != 'agent':
                redis_key = f"predefined:{self.room_name}:{self.user}"
                current_index = int(redis_client.get(redis_key) or 0)
                next_index = current_index + 1
                if next_index < len(self.predefined_messages):
                    redis_client.set(redis_key, next_index)
                    await self.send_predefined_message(next_index)
                    if next_index == 1:
                        await self.send_show_form_signal()
        except Exception as e:
            print(f"[ERROR] Handling new message: {e}")
            await self.send(text_data=json.dumps({'error': 'Failed to process message'}))

    async def send_predefined_message(self, index):
        if self.is_agent or index >= len(self.predefined_messages):
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

        try:
            insert_result = await sync_to_async(insert_with_timestamps)(collection, doc)
            if insert_result.inserted_id:
                print(f"[DB ✅] Predefined message inserted with ID: {insert_result.inserted_id}")
            else:
                print(f"[DB ❌] Predefined message insert failed for: {message_id}")

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': 'System',
                    'message_id': message_id,
                    'file_url': '',
                    'file_name': '',
                    'timestamp': timestamp.isoformat()
                }
            )
        except Exception as e:
            print(f"[ERROR] Sending predefined message: {e}")

    async def send_show_form_signal(self):
        print(f"[SHOW FORM] Sending form signal to room {self.room_group_name}")
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'show_form_signal',
                'show_form': True,
                'form_type': 'user_info'
            }
        )

    async def send_thank_you_message(self, name):
        collection = await sync_to_async(get_chat_collection)()
        message = f"Thank you {name}! Your information has been received."
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

        try:
            insert_result = await sync_to_async(insert_with_timestamps)(collection, doc)
            if insert_result.inserted_id:
                print(f"[DB ✅] Thank you message inserted with ID: {insert_result.inserted_id}")
            else:
                print(f"[DB ❌] Thank you message insert failed for: {message_id}")

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': 'System',
                    'message_id': message_id,
                    'file_url': '',
                    'file_name': '',
                    'timestamp': timestamp.isoformat()
                }
            )
        except Exception as e:
            print(f"[ERROR] Sending thank you message: {e}")

    async def chat_message(self, event):
        print(f"[SEND MESSAGE] {event}")
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'message_id': event['message_id'],
            'file_url': event.get('file_url', ''),
            'file_name': event.get('file_name', ''),
            'timestamp': event['timestamp'],
            'status': 'delivered',
            'form_data_received': event.get('form_data_received', False)
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

    async def show_form_signal(self, event):
        print(f"[SHOW FORM] Sending form signal to client: {event}")
        await self.send(text_data=json.dumps({
            'show_form': event['show_form'],
            'form_type': event['form_type']
        }))

    @sync_to_async
    def set_room_active_status(self, room_id, status: bool):
        try:
            collection = get_room_collection()
            collection.update_one(
                {'room_id': room_id},
                {'$set': {'is_active': status}},
                upsert=True
            )
            print(f"[DB ✅] Room {room_id} active status set to {status}")
        except Exception as e:
            print(f"[ERROR] Updating room status: {e}")