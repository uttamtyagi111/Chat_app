# import json
# import uuid
# from datetime import datetime, timedelta
# from channels.layers import get_channel_layer
# from channels.generic.websocket import AsyncWebsocketConsumer
# from wish_bot.db import (
#     get_chat_collection,
#     get_room_collection,
#     get_trigger_collection,
#     insert_with_timestamps,
#     get_contact_collection,
#     get_admin_collection,
# )
# from utils.redis_client import redis_client
# from asgiref.sync import sync_to_async
# from utils.random_id import generate_room_id, generate_contact_id
# import logging

# # Set up logging for debugging
# logger = logging.getLogger(__name__)

# def get_notifier():
#     return get_channel_layer()

# async def notify_event(event_type, payload):
#     channel_layer = get_notifier()
#     await channel_layer.group_send(
#         'notifications',
#         {
#             'type': 'notify',
#             'event_type': event_type,
#             'payload': payload,
#         }
#     )

# class ChatConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.room_name = self.scope['url_route']['kwargs']['room_id']
#         self.room_group_name = f'chat_{self.room_name}'
#         self.is_agent = 'agent=true' in self.scope.get('query_string', b'').decode()
#         self.user = f'user_{str(uuid.uuid4())}' if not self.is_agent else 'agent'

#         print(f"[DEBUG] Connection attempt - Room: {self.room_name}, Is Agent: {self.is_agent}, User: {self.user}")

#         room_valid = await sync_to_async(self.validate_room)()
#         print(f"[DEBUG] Room validation result: {room_valid}")
        
#         if not room_valid:
#             print(f"[DEBUG] Room {self.room_name} is not valid, closing connection")
#             await self.close()
#             return

#         # Only set room active status if this is a USER connection, not an agent
#         if not self.is_agent:
#             await self.set_room_active_status(self.room_name, True)
        
#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()
#         print(f"[DEBUG] WebSocket connection accepted for room: {self.room_name}")

#         if not self.is_agent:
#             await notify_event('new_room', {'room_id': self.room_name})
#             self.widget_id = await sync_to_async(self.get_widget_id_from_room)()
#             print(f"[DEBUG] Widget ID: {self.widget_id}")
            
#             self.triggers = await self.fetch_triggers_for_widget(self.widget_id)
#             print(f"[DEBUG] Fetched {len(self.triggers) if self.triggers else 0} triggers")
            
#             if self.triggers:
#                 for i, trigger in enumerate(self.triggers):
#                     print(f"[DEBUG] Trigger {i}: {trigger.get('message', '')[:50]}...")
            
#             redis_key = f"predefined:{self.room_name}:{self.user}"
#             redis_client.set(redis_key, 0)
#             print(f"[DEBUG] Set Redis key: {redis_key} = 0")
            
#             # Send first trigger message
#             await self.send_trigger_message(0)
#         else:
#             await self.send_chat_history()

#     def validate_room(self):
#         try:
#             room_collection = get_room_collection()
#             room = room_collection.find_one({'room_id': self.room_name})
#             print(f"[DEBUG] Room data: {room}")
            
#             if room is None:
#                 print(f"[DEBUG] Room {self.room_name} not found in database")
#                 return False
                
#             is_active = room.get('is_active', False)
#             print(f"[DEBUG] Room {self.room_name} is_active: {is_active}")
#             return is_active
#         except Exception as e:
#             print(f"[ERROR] Error validating room: {e}")
#             return False

#     def get_widget_id_from_room(self):
#         try:
#             room_collection = get_room_collection()
#             room = room_collection.find_one({'room_id': self.room_name})
#             widget_id = room.get('widget_id') if room else None
#             print(f"[DEBUG] Widget ID from room: {widget_id}")
#             return widget_id
#         except Exception as e:
#             print(f"[ERROR] Error getting widget ID: {e}")
#             return None

#     async def fetch_triggers_for_widget(self, widget_id):
#         try:
#             if not widget_id:
#                 print("[DEBUG] No widget_id provided, cannot fetch triggers")
#                 return []
                
#             collection = await sync_to_async(get_trigger_collection)()
#             triggers = await sync_to_async(lambda: list(
#                 collection.find({'widget_id': widget_id, 'is_active': True}).sort('order', 1)
#             ))()
#             print(f"[DEBUG] Fetched triggers for widget {widget_id}: {len(triggers)} triggers")
#             return triggers
#         except Exception as e:
#             print(f"[ERROR] Error fetching triggers: {e}")
#             return []

#     async def send_trigger_message(self, index):
#         try:
#             print(f"[DEBUG] send_trigger_message called with index: {index}")
            
#             if self.is_agent:
#                 print("[DEBUG] User is agent, skipping trigger message")
#                 return

#             if not hasattr(self, 'triggers') or not self.triggers:
#                 print("[DEBUG] No triggers available")
#                 return
                
#             if index >= len(self.triggers):
#                 print(f"[DEBUG] Index {index} >= triggers length {len(self.triggers)}, skipping")
#                 return

#             trigger = self.triggers[index]
#             message = trigger.get('message')
#             suggested_replies = trigger.get('suggested_replies', [])
#             timestamp = datetime.utcnow()
#             message_id = generate_room_id()

#             print(f"[DEBUG] Sending trigger message {index}: {message[:50] if message else 'No message'}...")

#             doc = {
#                 'message_id': message_id,
#                 'room_id': self.room_name,
#                 'sender': 'Wish-bot',
#                 'message': message,
#                 'file_url': '',
#                 'file_name': '',
#                 'delivered': True,
#                 'seen': False,
#                 'timestamp': timestamp
#             }

#             # Save to database
#             collection = await sync_to_async(get_chat_collection)()
#             await sync_to_async(insert_with_timestamps)(collection, doc)
#             print(f"[DEBUG] Trigger message saved to database with ID: {message_id}")

#             # Send to WebSocket group
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'chat_message',
#                     'message': message,
#                     'sender': 'Wish-bot',
#                     'message_id': message_id,
#                     'file_url': '',
#                     'file_name': '',
#                     'timestamp': timestamp.isoformat(),
#                     'suggested_replies': suggested_replies
#                 }
#             )
#             print(f"[DEBUG] Trigger message sent to group: {self.room_group_name}")
            
#         except Exception as e:
#             print(f"[ERROR] Error in send_trigger_message: {e}")
#             import traceback
#             traceback.print_exc()

#     async def disconnect(self, close_code):
#         print(f"[DEBUG] Disconnecting with close code: {close_code}")
#         if hasattr(self, 'room_name'):
#             # Only set room inactive status if this is a USER disconnection, not an agent
#             # if not self.is_agent:
#             #     await self.set_room_active_status(self.room_name, False)
            
#             # Clean up Redis keys regardless of user type
#             redis_client.delete(f'typing:{self.room_name}:{self.user}')
#             if not self.is_agent:
#                 redis_client.delete(f'predefined:{self.room_name}:{self.user}')
            
#             await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

#     async def receive(self, text_data):
#         try:
#             print(f"[DEBUG] Received data: {text_data[:100]}...")
#             data = json.loads(text_data)
#             collection = await sync_to_async(get_chat_collection)()

#             if not self.is_agent and (data.get('message') or data.get('file_url') or data.get('form_data')):
#                 rate_limit_key = f"rate_limit:{self.user}"
#                 current_time = datetime.now()
#                 last_message_time = redis_client.get(rate_limit_key)
#                 if last_message_time:
#                     try:
#                         last_message_time = datetime.fromisoformat(last_message_time)
#                         if (current_time - last_message_time) < timedelta(seconds=1):
#                             await self.send(text_data=json.dumps({'error': 'Rate limit exceeded.'}))
#                             return
#                     except ValueError:
#                         redis_client.delete(rate_limit_key)
#                 redis_client.setex(rate_limit_key, 60, current_time.isoformat())

#             if data.get('typing') is not None and 'content' in data:
#                 await self.handle_typing(data)
#                 return

#             if data.get('status') == 'seen' and data.get('message_id'):
#                 await self.handle_seen_status(data, collection)
#                 return

#             if data.get('form_data'):
#                 await self.handle_form_data(data, collection)
#                 return

#             if data.get('message') or data.get('file_url'):
#                 await self.handle_new_message(data, collection)

#         except json.JSONDecodeError as e:
#             print(f"[ERROR] JSON decode error: {e}")
#             await self.send(text_data=json.dumps({'error': 'Invalid message format'}))
#         except Exception as e:
#             print(f"[ERROR] Error in receive: {e}")
#             import traceback
#             traceback.print_exc()

#     async def handle_typing(self, data):
#         """Handle typing indicator from users"""
#         typing = data.get('typing', False)
#         content = data.get('content', '')
        
#         # Store typing status in Redis with expiration
#         typing_key = f'typing:{self.room_name}:{self.user}'
#         if typing:
#             redis_client.setex(typing_key, 10, content)  # Expire after 10 seconds
#         else:
#             redis_client.delete(typing_key)
        
#         # Broadcast typing status to other users in the room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 'type': 'typing_status',
#                 'typing': typing,
#                 'content': content,
#                 'sender': self.user,
#                 'is_agent': self.is_agent
#             }
#         )

#     async def handle_seen_status(self, data, collection):
#         """Handle message seen status updates"""
#         message_id = data.get('message_id')
#         sender = data.get('sender', self.user)
        
#         if not message_id:
#             return
        
#         try:
#             # Update the message as seen in database
#             await sync_to_async(collection.update_one)(
#                 {'message_id': message_id, 'room_id': self.room_name},
#                 {'$set': {'seen': True, 'seen_at': datetime.utcnow()}}
#             )
            
#             # Broadcast seen status to other users in the room
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'message_seen',
#                     'message_id': message_id,
#                     'sender': sender,
#                     'timestamp': datetime.utcnow().isoformat()
#                 }
#             )
#         except Exception as e:
#             print(f"[ERROR] Updating seen status: {e}")

#     async def handle_form_data(self, data, collection):
#         """Handle form data submission from users"""
#         form_data = data.get('form_data', {})
#         message_id = data.get('message_id') or generate_room_id()
#         timestamp = datetime.utcnow()
        
#         # Extract form fields
#         name = form_data.get('name', '')
#         email = form_data.get('email', '')
#         phone = form_data.get('phone', '')
        
#         # Save contact information
#         try:
#             contact_collection = await sync_to_async(get_contact_collection)()
            
#             room_collection = await sync_to_async(get_room_collection)()
#             room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
#             contact_id = room.get('contact_id') if room and room.get('contact_id') else generate_contact_id()

            
#             contact_doc = {
#                 'contact_id': contact_id,
#                 'room_id': self.room_name,
#                 'name': name,
#                 'email': email,
#                 'phone': phone,
#                 'widget_id': getattr(self, 'widget_id', None),
#                 'timestamp': timestamp
#             }
#             await sync_to_async(insert_with_timestamps)(contact_collection, contact_doc)
            
#             # Create a message indicating form submission
#             message = f"Contact information submitted: {name} ({email})"
#             doc = {
#                 'message_id': message_id,
#                 'room_id': self.room_name,
#                 'contact_id': contact_id,
#                 'sender': self.user,
#                 'message': message,
#                 'file_url': '',
#                 'file_name': '',
#                 'delivered': True,
#                 'seen': False,
#                 'timestamp': timestamp,
#                 'form_data': form_data
#             }
            
#             await sync_to_async(insert_with_timestamps)(collection, doc)
            
#             # Broadcast the form submission
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'chat_message',
#                     'message': message,
#                     'contact_id': contact_id,
#                     'sender': self.user,
#                     'message_id': message_id,
#                     'file_url': '',
#                     'file_name': '',
#                     'timestamp': timestamp.isoformat(),
#                     'form_data': form_data
#                 }
#             )
            
#             # Notify about new contact
#             await notify_event('new_contact', {
#                 'room_id': self.room_name,
#                 'contact_info': contact_doc
#             })
            
#         except Exception as e:
#             print(f"[ERROR] Handling form data: {e}")
#             await self.send(text_data=json.dumps({
#                 'error': 'Failed to submit form data'
#             }))

#     async def handle_new_message(self, data, collection):
#         assigned_agent_id = None
#         try:
#             message_id = data.get('message_id') or generate_room_id()
#             timestamp = datetime.utcnow()
#             # contact_id = data.get('contact_id') or generate_contact_id()
#             contact_id = data.get('contact_id')
#             if not contact_id:
#                 # Try to get from room data
#                 room_collection = await sync_to_async(get_room_collection)()
#                 room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
#                 contact_id = room.get('contact_id') if room else generate_contact_id()
#             if not contact_id:
#                 print("[ERROR] No contact_id provided, cannot handle new message")
#                 return
#             sender = data.get('sender', self.user)
#             message = data.get('message', '')
#             file_url = data.get('file_url', '')
#             file_name = data.get('file_name', '')
            
#             # Initialize display_sender_name with the original sender
#             display_sender_name = sender
            
#             if sender == 'agent':
#                 room_collection = await sync_to_async(get_room_collection)()
#                 room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
#                 assigned_agent_id = room.get('assigned_agent') if room else None

#             if assigned_agent_id:
#                 admin_collection = await sync_to_async(get_admin_collection)()
#                 agent_doc = await sync_to_async(lambda: admin_collection.find_one({'admin_id': assigned_agent_id}))()
#                 agent_name = agent_doc.get('name') if agent_doc else 'Agent'
#                 sender = agent_name
#             else:
#                 sender = 'Agent'

#             print(f"[DEBUG] Handling new message from {display_sender_name}: {message[:50]}...")

#             doc = {
#                 'message_id': message_id,
#                 'room_id': self.room_name,
#                 'contact_id': contact_id,
#                 'sender': display_sender_name,
#                 'message': message,
#                 'file_url': file_url,
#                 'file_name': file_name,
#                 'delivered': True,
#                 'seen': False,
#                 'timestamp': timestamp
#             }

#             await sync_to_async(insert_with_timestamps)(collection, doc)

#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'chat_message',
#                     'message': message,
#                     'contact_id': contact_id,
#                     'sender': display_sender_name,
#                     'message_id': message_id,
#                     'file_url': file_url,
#                     'file_name': file_name,
#                     'timestamp': timestamp.isoformat()
#                 }
#             )

#             await notify_event('new_message', {**doc, 'timestamp': timestamp.isoformat()})

#             # Handle trigger progression for non-agent users
#             if not self.is_agent and sender != 'agent':
#                 print(f"[DEBUG] Processing trigger progression for user message")
#                 redis_key = f"predefined:{self.room_name}:{self.user}"
#                 current_index = int(redis_client.get(redis_key) or 0)
#                 next_index = current_index + 1
                
#                 print(f"[DEBUG] Current trigger index: {current_index}, Next: {next_index}")
#                 print(f"[DEBUG] Total triggers available: {len(self.triggers) if hasattr(self, 'triggers') and self.triggers else 0}")
                
#                 if hasattr(self, 'triggers') and self.triggers and next_index < len(self.triggers):
#                     redis_client.set(redis_key, next_index)
#                     print(f"[DEBUG] Updated Redis key {redis_key} to {next_index}")
                    
#                     # Add a small delay to ensure message ordering
#                     import asyncio
#                     await asyncio.sleep(0.5)
                    
#                     await self.send_trigger_message(next_index)
                    
#                     if next_index == 1:  # Show form after second trigger
#                         await self.send_show_form_signal()
#                 else:
#                     print(f"[DEBUG] No more triggers to send or triggers not available")
                    
#         except Exception as e:
#             print(f"[ERROR] Error in handle_new_message: {e}")
#             import traceback
#             traceback.print_exc()
            
#     async def agent_assigned(self, event):
#         """Handle agent assignment notification"""
#         try:
#             await self.send(text_data=json.dumps({
#                 'type': 'agent_assigned',
#                 'agent_name': event['agent_name'],
#                 'agent_id': event['agent_id'],
#                 'message': event['message'],
#                 'timestamp': datetime.utcnow().isoformat()
#             }))
#         except Exception as e:
#             print(f"[ERROR] Error in agent_assigned: {e}")

#     async def send_chat_history(self):
#         try:
#             print(f"[DEBUG] Sending chat history for room: {self.room_name}")
#             collection = await sync_to_async(get_chat_collection)()
#             messages = await sync_to_async(lambda: list(
#                 collection.find({'room_id': self.room_name}, {'_id': 0}).sort('timestamp', 1)
#             ))()

#             print(f"[DEBUG] Found {len(messages)} messages in history")

#             for msg in messages:
#                 if isinstance(msg.get('timestamp'), datetime):
#                     msg['timestamp'] = msg['timestamp'].isoformat()
#                 await self.send(text_data=json.dumps({
#                     'message': msg.get('message', ''),
#                     'sender': msg.get('sender', 'unknown'),
#                     'message_id': msg.get('message_id', ''),
#                     'file_url': msg.get('file_url', ''),
#                     'file_name': msg.get('file_name', ''),
#                     'timestamp': msg.get('timestamp', ''),
#                     'status': 'history',
#                     'contact_id': msg.get('contact_id', '')
#                 }))
#         except Exception as e:
#             print(f"[ERROR] Error sending chat history: {e}")
# #
#     async def send_show_form_signal(self):
#         """Send signal to show contact form"""
#         try:
#             print("[DEBUG] Sending show form signal")
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     'type': 'show_form_signal',
#                     'show_form': True,
#                     'form_type': 'contact'
#                 }
#             )
#         except Exception as e:
#             print(f"[ERROR] Error sending show form signal: {e}")

#     async def chat_message(self, event):
#         try:
#             print(f"[DEBUG] Broadcasting chat message: {event.get('message', '')[:50]}...")
#             await self.send(text_data=json.dumps({
#                 'message': event['message'],
#                 'sender': event['sender'],
#                 'message_id': event['message_id'],
#                 'file_url': event.get('file_url', ''),
#                 'file_name': event.get('file_name', ''),
#                 'timestamp': event['timestamp'],
#                 'status': 'delivered',
#                 'suggested_replies': event.get('suggested_replies', []),
#                 'contact_id': event.get('contact_id', '')
#             }))
#         except Exception as e:
#             print(f"[ERROR] Error in chat_message: {e}")

#     async def typing_status(self, event):
#         if event['sender'] != self.user:
#             display_name = "Agent" if event.get('is_agent', False) else "User"
            
#             await self.send(text_data=json.dumps({
#                 'typing': event['typing'],
#                 'content': event.get('content', ''),
#                 'sender': event['sender'],
#                 'sender': display_name,  # Clean display name (User/Agent)
#                 'original_sender': event['sender']  # Keep original sender ID if needed
#             }))

#     async def message_seen(self, event):
#         await self.send(text_data=json.dumps({
#             'message_id': event['message_id'],
#             'status': 'seen',
#             'sender': event['sender'],
#             'timestamp': event['timestamp'],
#             'contact_id': event.get('contact_id', '')
#         }))

#     async def show_form_signal(self, event):
#         try:
#             print(f"[DEBUG] Sending show form signal to client: {event}")
#             await self.send(text_data=json.dumps({
#                 'show_form': event['show_form'],  
#                 'form_type': event['form_type']
#             }))
#         except Exception as e:
#             print(f"[ERROR] Error in show_form_signal: {e}")

#     @sync_to_async
#     def set_room_active_status(self, room_id, status: bool):
#         try:
#             collection = get_room_collection()
#             result = collection.update_one(
#                 {'room_id': room_id},
#                 {'$set': {'is_active': status}},
#                 upsert=True
#             )
#             print(f"[DEBUG] Room status update result: {result.modified_count} modified, {result.upserted_id} upserted")
#         except Exception as e:
#             print(f"[ERROR] Updating room status: {e}")


import json
import uuid
from datetime import datetime, timedelta
from channels.layers import get_channel_layer
from channels.generic.websocket import AsyncWebsocketConsumer
from wish_bot.db import (
    get_chat_collection,
    get_room_collection,
    get_trigger_collection,
    insert_with_timestamps,
    get_contact_collection,
    get_admin_collection,
)
from utils.redis_client import redis_client
from asgiref.sync import sync_to_async
from utils.random_id import generate_room_id, generate_contact_id
import logging

# Set up logging for debugging
logger = logging.getLogger(__name__)

def get_notifier():
    return get_channel_layer()

async def notify_event(event_type, payload):
    channel_layer = get_notifier()
    # Send different types of notifications to appropriate groups
    if event_type in ['room_list_update', 'new_message_agent', 'unread_update', 'agent_status_change']:
        group = 'notifications_agent'
    else:
        group = 'notifications'
    
    await channel_layer.group_send(
        group,
        {
            'type': 'notify',
            'event_type': event_type,
            'payload': payload,
        }
    )

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_name}'
        self.is_agent = 'agent=true' in self.scope.get('query_string', b'').decode()
        self.user = f'user_{str(uuid.uuid4())}' if not self.is_agent else 'agent'
        self.agent_id = self.scope.get('url_route', {}).get('kwargs', {}).get('agent_id') if self.is_agent else None

        print(f"[DEBUG] Connection attempt - Room: {self.room_name}, Is Agent: {self.is_agent}, User: {self.user}")

        room_valid = await sync_to_async(self.validate_room)()
        print(f"[DEBUG] Room validation result: {room_valid}")
        
        if not room_valid:
            print(f"[DEBUG] Room {self.room_name} is not valid, closing connection")
            await self.close()
            return

        # Only set room active status if this is a USER connection, not an agent
        if not self.is_agent:
            await self.set_room_active_status(self.room_name, True)
        
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        
        # Subscribe agent to notifications and set online status
        if self.is_agent:
            await self.channel_layer.group_add('notifications_agent', self.channel_name)
            await self.set_agent_online_status(True)
        
        await self.accept()
        print(f"[DEBUG] WebSocket connection accepted for room: {self.room_name}")

        if not self.is_agent:
            # Notify agents about new room/user connection
            await notify_event('new_room', {
                'room_id': self.room_name,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            self.widget_id = await sync_to_async(self.get_widget_id_from_room)()
            print(f"[DEBUG] Widget ID: {self.widget_id}")
            
            self.triggers = await self.fetch_triggers_for_widget(self.widget_id)
            print(f"[DEBUG] Fetched {len(self.triggers) if self.triggers else 0} triggers")
            
            redis_key = f"predefined:{self.room_name}:{self.user}"
            redis_client.set(redis_key, 0)
            print(f"[DEBUG] Set Redis key: {redis_key} = 0")
            
            # Send first trigger message
            await self.send_trigger_message(0)
        else:
            await self.send_chat_history()
            # Send initial room list to newly connected agent
            await self.send_room_list()

    def validate_room(self):
        try:
            room_collection = get_room_collection()
            room = room_collection.find_one({'room_id': self.room_name})
            print(f"[DEBUG] Room data: {room}")
            
            if room is None:
                print(f"[DEBUG] Room {self.room_name} not found in database")
                return False
                
            is_active = room.get('is_active', False)
            print(f"[DEBUG] Room {self.room_name} is_active: {is_active}")
            return is_active
        except Exception as e:
            print(f"[ERROR] Error validating room: {e}")
            return False

    def get_widget_id_from_room(self):
        try:
            room_collection = get_room_collection()
            room = room_collection.find_one({'room_id': self.room_name})
            widget_id = room.get('widget_id') if room else None
            print(f"[DEBUG] Widget ID from room: {widget_id}")
            return widget_id
        except Exception as e:
            print(f"[ERROR] Error getting widget ID: {e}")
            return None

    async def set_agent_online_status(self, is_online):
        """Set agent online/offline status in Redis"""
        try:
            if self.is_agent and self.agent_id:
                status_key = f"agent_online:{self.agent_id}"
                if is_online:
                    redis_client.setex(status_key, 3600, datetime.utcnow().isoformat())  # 1 hour expiry
                else:
                    redis_client.delete(status_key)
                
                # Notify about agent status change
                await notify_event('agent_status_change', {
                    'agent_id': self.agent_id,
                    'status': 'online' if is_online else 'offline',
                    'timestamp': datetime.utcnow().isoformat()
                })
        except Exception as e:
            print(f"[ERROR] Setting agent online status: {e}")

    async def fetch_triggers_for_widget(self, widget_id):
        try:
            if not widget_id:
                print("[DEBUG] No widget_id provided, cannot fetch triggers")
                return []
                
            collection = await sync_to_async(get_trigger_collection)()
            triggers = await sync_to_async(lambda: list(
                collection.find({'widget_id': widget_id, 'is_active': True}).sort('order', 1)
            ))()
            print(f"[DEBUG] Fetched triggers for widget {widget_id}: {len(triggers)} triggers")
            return triggers
        except Exception as e:
            print(f"[ERROR] Error fetching triggers: {e}")
            return []

    async def send_trigger_message(self, index):
        try:
            print(f"[DEBUG] send_trigger_message called with index: {index}")
            
            if self.is_agent:
                print("[DEBUG] User is agent, skipping trigger message")
                return

            if not hasattr(self, 'triggers') or not self.triggers:
                print("[DEBUG] No triggers available")
                return
                
            if index >= len(self.triggers):
                print(f"[DEBUG] Index {index} >= triggers length {len(self.triggers)}, skipping")
                return

            trigger = self.triggers[index]
            message = trigger.get('message')
            suggested_replies = trigger.get('suggested_replies', [])
            timestamp = datetime.utcnow()
            message_id = generate_room_id()

            print(f"[DEBUG] Sending trigger message {index}: {message[:50] if message else 'No message'}...")

            doc = {
                'message_id': message_id,
                'room_id': self.room_name,
                'sender': 'Wish-bot',
                'message': message,
                'file_url': '',
                'file_name': '',
                'delivered': True,
                'seen': False,
                'timestamp': timestamp
            }

            # Save to database
            collection = await sync_to_async(get_chat_collection)()
            await sync_to_async(insert_with_timestamps)(collection, doc)
            print(f"[DEBUG] Trigger message saved to database with ID: {message_id}")

            # Send to WebSocket group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': 'Wish-bot',
                    'message_id': message_id,
                    'file_url': '',
                    'file_name': '',
                    'timestamp': timestamp.isoformat(),
                    'suggested_replies': suggested_replies
                }
            )
            print(f"[DEBUG] Trigger message sent to group: {self.room_group_name}")
            
        except Exception as e:
            print(f"[ERROR] Error in send_trigger_message: {e}")
            import traceback
            traceback.print_exc()

    async def disconnect(self, close_code):
        print(f"[DEBUG] Disconnecting with close code: {close_code}")
        if hasattr(self, 'room_name'):
            # Set agent offline status
            if self.is_agent:
                await self.set_agent_online_status(False)
            
            # Clean up Redis keys regardless of user type
            redis_client.delete(f'typing:{self.room_name}:{self.user}')
            if not self.is_agent:
                redis_client.delete(f'predefined:{self.room_name}:{self.user}')
            
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            
            # Unsubscribe agent from notifications
            if self.is_agent:
                await self.channel_layer.group_discard('notifications_agent', self.channel_name)

    async def receive(self, text_data):
        try:
            print(f"[DEBUG] Received data: {text_data[:100]}...")
            data = json.loads(text_data)
            collection = await sync_to_async(get_chat_collection)()

            # Handle agent room list request
            if data.get('action') == 'get_room_list' and self.is_agent:
                await self.send_room_list()
                return

            # Handle agent heartbeat for online status
            if data.get('action') == 'heartbeat' and self.is_agent:
                await self.set_agent_online_status(True)
                return

            # Handle mark all messages as read for a room
            if data.get('action') == 'mark_room_read' and self.is_agent:
                room_id = data.get('room_id', self.room_name)
                await self.mark_room_messages_read(room_id)
                return

            if not self.is_agent and (data.get('message') or data.get('file_url') or data.get('form_data')):
                rate_limit_key = f"rate_limit:{self.user}"
                current_time = datetime.now()
                last_message_time = redis_client.get(rate_limit_key)
                if last_message_time:
                    try:
                        last_message_time = datetime.fromisoformat(last_message_time)
                        if (current_time - last_message_time) < timedelta(seconds=1):
                            await self.send(text_data=json.dumps({'error': 'Rate limit exceeded.'}))
                            return
                    except ValueError:
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
            print(f"[ERROR] JSON decode error: {e}")
            await self.send(text_data=json.dumps({'error': 'Invalid message format'}))
        except Exception as e:
            print(f"[ERROR] Error in receive: {e}")
            import traceback
            traceback.print_exc()

    async def mark_room_messages_read(self, room_id):
        """Mark all messages in a room as read by agent"""
        try:
            collection = await sync_to_async(get_chat_collection)()
            
            # Update all unread messages in the room
            await sync_to_async(collection.update_many)(
                {'room_id': room_id, 'seen': False, 'sender': {'$ne': 'agent'}},
                {'$set': {'seen': True, 'seen_at': datetime.utcnow()}}
            )
            
            # Reset unread count
            unread_key = f'unread:{room_id}'
            redis_client.delete(unread_key)
            
            # Notify about unread count update
            await notify_event('unread_update', {
                'room_id': room_id,
                'unread_count': 0,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            print(f"[DEBUG] Marked all messages as read for room: {room_id}")
            
        except Exception as e:
            print(f"[ERROR] Error marking room messages as read: {e}")

    async def handle_typing(self, data):
        """Handle typing indicator from users"""
        typing = data.get('typing', False)
        content = data.get('content', '')
        
        # Store typing status in Redis with expiration
        typing_key = f'typing:{self.room_name}:{self.user}'
        if typing:
            redis_client.setex(typing_key, 10, content)  # Expire after 10 seconds
        else:
            redis_client.delete(typing_key)
        
        # Broadcast typing status to other users in the room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'typing_status',
                'typing': typing,
                'content': content,
                'sender': self.user,
                'is_agent': self.is_agent
            }
        )

    async def handle_seen_status(self, data, collection):
        """Handle message seen status updates"""
        message_id = data.get('message_id')
        sender = data.get('sender', self.user)
        
        if not message_id:
            return
        
        try:
            # Update the message as seen in database
            result = await sync_to_async(collection.update_one)(
                {'message_id': message_id, 'room_id': self.room_name},
                {'$set': {'seen': True, 'seen_at': datetime.utcnow()}}
            )
            
            # If agent saw the message, update unread count
            if self.is_agent and result.modified_count > 0:
                unread_key = f'unread:{self.room_name}'
                current_unread = int(redis_client.get(unread_key) or 0)
                if current_unread > 0:
                    new_unread = max(0, current_unread - 1)
                    if new_unread == 0:
                        redis_client.delete(unread_key)
                    else:
                        redis_client.set(unread_key, new_unread)
                    
                    # Notify about unread count update
                    await notify_event('unread_update', {
                        'room_id': self.room_name,
                        'unread_count': new_unread,
                        'timestamp': datetime.utcnow().isoformat()
                    })
            
            # Broadcast seen status to other users in the room
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_seen',
                    'message_id': message_id,
                    'sender': sender,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            print(f"[ERROR] Updating seen status: {e}")

    async def handle_form_data(self, data, collection):
        """Handle form data submission from users"""
        form_data = data.get('form_data', {})
        message_id = data.get('message_id') or generate_room_id()
        timestamp = datetime.utcnow()
        
        # Extract form fields
        name = form_data.get('name', '')
        email = form_data.get('email', '')
        phone = form_data.get('phone', '')
        
        # Save contact information
        try:
            contact_collection = await sync_to_async(get_contact_collection)()
            
            room_collection = await sync_to_async(get_room_collection)()
            room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
            contact_id = room.get('contact_id') if room and room.get('contact_id') else generate_contact_id()

            contact_doc = {
                'contact_id': contact_id,
                'room_id': self.room_name,
                'name': name,
                'email': email,
                'phone': phone,
                'widget_id': getattr(self, 'widget_id', None),
                'timestamp': timestamp
            }
            await sync_to_async(insert_with_timestamps)(contact_collection, contact_doc)
            
            # Create a message indicating form submission
            message = f"Contact information submitted: {name} ({email})"
            doc = {
                'message_id': message_id,
                'room_id': self.room_name,
                'contact_id': contact_id,
                'sender': self.user,
                'message': message,
                'file_url': '',
                'file_name': '',
                'delivered': True,
                'seen': False,
                'timestamp': timestamp,
                'form_data': form_data
            }
            
            await sync_to_async(insert_with_timestamps)(collection, doc)
            
            # Increment unread count for non-agent messages
            if not self.is_agent:
                unread_key = f'unread:{self.room_name}'
                new_unread_count = redis_client.incr(unread_key)
                
                # Notify agents about new unread message
                await notify_event('unread_update', {
                    'room_id': self.room_name,
                    'unread_count': new_unread_count,
                    'timestamp': timestamp.isoformat()
                })
            
            # Broadcast the form submission
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'contact_id': contact_id,
                    'sender': self.user,
                    'message_id': message_id,
                    'file_url': '',
                    'file_name': '',
                    'timestamp': timestamp.isoformat(),
                    'form_data': form_data
                }
            )
            
            # Notify about new contact and trigger room list update
            await notify_event('new_contact', {
                'room_id': self.room_name,
                'contact_info': contact_doc,
                'timestamp': timestamp.isoformat()
            })
            
            await notify_event('room_list_update', {
                'room_id': self.room_name,
                'action': 'contact_added',
                'timestamp': timestamp.isoformat()
            })
            
        except Exception as e:
            print(f"[ERROR] Handling form data: {e}")
            await self.send(text_data=json.dumps({
                'error': 'Failed to submit form data'
            }))

    async def handle_new_message(self, data, collection):
        assigned_agent_id = None
        try:
            message_id = data.get('message_id') or generate_room_id()
            timestamp = datetime.utcnow()
            contact_id = data.get('contact_id')
            
            if not contact_id:
                # Try to get from room data
                room_collection = await sync_to_async(get_room_collection)()
                room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
                contact_id = room.get('contact_id') if room else generate_contact_id()
            
            if not contact_id:
                print("[ERROR] No contact_id provided, cannot handle new message")
                return
                
            sender = data.get('sender', self.user)
            message = data.get('message', '')
            file_url = data.get('file_url', '')
            file_name = data.get('file_name', '')
            
            # Initialize display_sender_name with the original sender
            display_sender_name = sender
            
            if sender == 'agent':
                room_collection = await sync_to_async(get_room_collection)()
                room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
                assigned_agent_id = room.get('assigned_agent') if room else None

                if assigned_agent_id:
                    admin_collection = await sync_to_async(get_admin_collection)()
                    agent_doc = await sync_to_async(lambda: admin_collection.find_one({'admin_id': assigned_agent_id}))()
                    agent_name = agent_doc.get('name') if agent_doc else 'Agent'
                    display_sender_name = agent_name
                else:
                    display_sender_name = 'Agent'

            print(f"[DEBUG] Handling new message from {display_sender_name}: {message[:50]}...")

            doc = {
                'message_id': message_id,
                'room_id': self.room_name,
                'contact_id': contact_id,
                'sender': display_sender_name,
                'message': message,
                'file_url': file_url,
                'file_name': file_name,
                'delivered': True,
                'seen': False,
                'timestamp': timestamp
            }

            await sync_to_async(insert_with_timestamps)(collection, doc)

            # Handle unread count and notifications for non-agent messages
            if not self.is_agent:
                unread_key = f'unread:{self.room_name}'
                new_unread_count = redis_client.incr(unread_key)
                
                # Notify agents about new message with enhanced payload
                await notify_event('new_message_agent', {
                    'room_id': self.room_name,
                    'message': message,
                    'sender': display_sender_name,
                    'message_id': message_id,
                    'contact_id': contact_id,
                    'unread_count': new_unread_count,
                    'timestamp': timestamp.isoformat(),
                    'file_url': file_url,
                    'file_name': file_name
                })
                
                # Also notify about unread count update
                await notify_event('unread_update', {
                    'room_id': self.room_name,
                    'unread_count': new_unread_count,
                    'timestamp': timestamp.isoformat()
                })

            # Broadcast message to room participants
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'contact_id': contact_id,
                    'sender': display_sender_name,
                    'message_id': message_id,
                    'file_url': file_url,
                    'file_name': file_name,
                    'timestamp': timestamp.isoformat()
                }
            )

            # Notify general event (keep existing for compatibility)
            await notify_event('new_message', {**doc, 'timestamp': timestamp.isoformat()})

            # Trigger room list update for agents
            if not self.is_agent:
                await notify_event('room_list_update', {
                    'room_id': self.room_name,
                    'action': 'new_message',
                    'timestamp': timestamp.isoformat()
                })

            # Handle trigger progression for non-agent users
            if not self.is_agent and sender != 'agent':
                print(f"[DEBUG] Processing trigger progression for user message")
                redis_key = f"predefined:{self.room_name}:{self.user}"
                current_index = int(redis_client.get(redis_key) or 0)
                next_index = current_index + 1
                
                print(f"[DEBUG] Current trigger index: {current_index}, Next: {next_index}")
                print(f"[DEBUG] Total triggers available: {len(self.triggers) if hasattr(self, 'triggers') and self.triggers else 0}")
                
                if hasattr(self, 'triggers') and self.triggers and next_index < len(self.triggers):
                    redis_client.set(redis_key, next_index)
                    print(f"[DEBUG] Updated Redis key {redis_key} to {next_index}")
                    
                    # Add a small delay to ensure message ordering
                    import asyncio
                    await asyncio.sleep(0.5)
                    
                    await self.send_trigger_message(next_index)
                    
                    if next_index == 1:  # Show form after second trigger
                        await self.send_show_form_signal()
                else:
                    print(f"[DEBUG] No more triggers to send or triggers not available")
                    
        except Exception as e:
            print(f"[ERROR] Error in handle_new_message: {e}")
            import traceback
            traceback.print_exc()

    async def get_room_unread_counts(self):
        """Get unread counts for all active rooms"""
        try:
            room_collection = await sync_to_async(get_room_collection)()
            rooms = await sync_to_async(lambda: list(
                room_collection.find({'is_active': True}, {'room_id': 1})
            ))()
            
            unread_counts = {}
            for room in rooms:
                room_id = room['room_id']
                unread_key = f'unread:{room_id}'
                unread_count = int(redis_client.get(unread_key) or 0)
                if unread_count > 0:
                    unread_counts[room_id] = unread_count
            
            return unread_counts
        except Exception as e:
            print(f"[ERROR] Getting room unread counts: {e}")
            return {}

    async def agent_assigned(self, event):
        """Handle agent assignment notification"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'agent_assigned',
                'agent_name': event['agent_name'],
                'agent_id': event['agent_id'],
                'message': event['message'],
                'timestamp': datetime.utcnow().isoformat()
            }))
        except Exception as e:
            print(f"[ERROR] Error in agent_assigned: {e}")

    async def send_chat_history(self):
        try:
            print(f"[DEBUG] Sending chat history for room: {self.room_name}")
            collection = await sync_to_async(get_chat_collection)()
            messages = await sync_to_async(lambda: list(
                collection.find({'room_id': self.room_name}, {'_id': 0}).sort('timestamp', 1)
            ))()

            print(f"[DEBUG] Found {len(messages)} messages in history")

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
                    'status': 'history',
                    'contact_id': msg.get('contact_id', '')
                }))
        except Exception as e:
            print(f"[ERROR] Error sending chat history: {e}")

    async def send_room_list(self):
        try:
            room_collection = await sync_to_async(get_room_collection)()
            chat_collection = await sync_to_async(get_chat_collection)()
            contact_collection = await sync_to_async(get_contact_collection)()

            rooms = await sync_to_async(lambda: list(
                room_collection.find({'is_active': True})
            ))()

            room_list = []
            total_unread = 0
            
            for room in rooms:
                room_id = room['room_id']
                assigned_agent = room.get('assigned_agent')

                # Optional: Filter by agent ID in production
                if self.is_agent and assigned_agent not in [None, 'agent', 'superadmin']:
                    pass

                last_message = await sync_to_async(lambda: chat_collection.find_one(
                    {'room_id': room_id},
                    sort=[('timestamp', -1)]
                ))()

                contact_doc = await sync_to_async(lambda: contact_collection.find_one({'room_id': room_id}))()
                unread_key = f'unread:{room_id}'
                unread_count = int(redis_client.get(unread_key) or 0)
                total_unread += unread_count

                room_info = {
                    'room_id': room_id,
                    'widget_id': room.get('widget_id'),
                    'contact': {
                        'name': contact_doc.get('name') if contact_doc else '',
                        'email': contact_doc.get('email') if contact_doc else '',
                        'phone': contact_doc.get('phone') if contact_doc else ''
                    },
                    'latest_message': last_message.get('message') if last_message else '',
                    'latest_message_sender': last_message.get('sender') if last_message else '',
                    'timestamp': last_message.get('timestamp').isoformat() if last_message and last_message.get('timestamp') else '',
                    'unread_count': unread_count,
                    'has_unread': unread_count > 0,
                    'assigned_agent': assigned_agent
                }

                room_list.append(room_info)

            # Sort rooms by latest message timestamp (most recent first)
            room_list.sort(key=lambda x: x['timestamp'], reverse=True)

            await self.send(text_data=json.dumps({
                'type': 'room_list',
                'rooms': room_list,
                'total_unread': total_unread,
                'timestamp': datetime.utcnow().isoformat()
            }))
        except Exception as e:
            print(f"[ERROR] Failed to send room list: {e}")

    async def send_show_form_signal(self):
        """Send signal to show contact form"""
        try:
            print("[DEBUG] Sending show form signal")
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'show_form_signal',
                    'show_form': True,
                    'form_type': 'contact'
                }
            )
        except Exception as e:
            print(f"[ERROR] Error sending show form signal: {e}")

    async def notify(self, event):
        """Handle notifications sent to agents"""
        event_type = event.get('event_type')
        payload = event.get('payload', {})

        try:
            if self.is_agent:
                if event_type == 'room_list_update':
                    await self.send_room_list()
                elif event_type == 'new_message_agent':
                    # Send real-time notification for new message
                    await self.send(text_data=json.dumps({
                        'type': 'new_message_notification',
                        'room_id': payload.get('room_id'),
                        'message': payload.get('message'),
                        'sender': payload.get('sender'),
                        'message_id': payload.get('message_id'),
                        'contact_id': payload.get('contact_id'),
                        'unread_count': payload.get('unread_count'),
                        'timestamp': payload.get('timestamp'),
                        'file_url': payload.get('file_url', ''),
                        'file_name': payload.get('file_name', '')
                    }))
                elif event_type == 'unread_update':
                    # Send unread count update
                    await self.send(text_data=json.dumps({
                        'type': 'unread_update',
                        'room_id': payload.get('room_id'),
                        'unread_count': payload.get('unread_count'),
                        'timestamp': payload.get('timestamp')
                    }))
                elif event_type == 'new_contact':
                    # Send new contact notification
                    await self.send(text_data=json.dumps({
                        'type': 'new_contact_notification',
                        'room_id': payload.get('room_id'),
                        'contact_info': payload.get('contact_info'),
                        'timestamp': payload.get('timestamp')
                    }))
                elif event_type == 'agent_status_change':
                    # Send agent status change notification
                    await self.send(text_data=json.dumps({
                        'type': 'agent_status_change',
                        'agent_id': payload.get('agent_id'),
                        'status': payload.get('status'),
                        'timestamp': payload.get('timestamp')
                    }))
                elif event_type == 'new_room':
                    # Send new room notification
                    await self.send(text_data=json.dumps({
                        'type': 'new_room_notification',
                        'room_id': payload.get('room_id'),
                        'timestamp': payload.get('timestamp')
                    }))
        except Exception as e:
            print(f"[ERROR] Error in notify: {e}")

    async def chat_message(self, event):
        try:
            print(f"[DEBUG] Broadcasting chat message: {event.get('message', '')[:50]}...")
            await self.send(text_data=json.dumps({
                'message': event['message'],
                'sender': event['sender'],
                'message_id': event['message_id'],
                'file_url': event.get('file_url', ''),
                'file_name': event.get('file_name', ''),
                'timestamp': event['timestamp'],
                'status': 'delivered',
                'suggested_replies': event.get('suggested_replies', []),
                'contact_id': event.get('contact_id', '')
            }))
        except Exception as e:
            print(f"[ERROR] Error in chat_message: {e}")

    async def typing_status(self, event):
        if event['sender'] != self.user:
            display_name = "Agent" if event.get('is_agent', False) else "User"
            
            await self.send(text_data=json.dumps({
                'type': 'typing_status',
                'typing': event['typing'],
                'content': event.get('content', ''),
                'sender': display_name,
                'original_sender': event['sender']
            }))

    async def message_seen(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_seen',
            'message_id': event['message_id'],
            'status': 'seen',
            'sender': event['sender'],
            'timestamp': event['timestamp'],
            'contact_id': event.get('contact_id', '')
        }))

    async def show_form_signal(self, event):
        try:
            print(f"[DEBUG] Sending show form signal to client: {event}")
            await self.send(text_data=json.dumps({
                'type': 'show_form_signal',
                'show_form': event['show_form'],  
                'form_type': event['form_type']
            }))
        except Exception as e:
            print(f"[ERROR] Error in show_form_signal: {e}")

    @sync_to_async
    def set_room_active_status(self, room_id, status: bool):
        try:
            collection = get_room_collection()
            result = collection.update_one(
                {'room_id': room_id},
                {'$set': {'is_active': status}},
                upsert=True
            )
            print(f"[DEBUG] Room status update result: {result.modified_count} modified, {result.upserted_id} upserted")
        except Exception as e:
            print(f"[ERROR] Updating room status: {e}")


# Additional utility functions for enhanced notifications

class NotificationConsumer(AsyncWebsocketConsumer):
    """Dedicated consumer for agent dashboard notifications"""
    
    async def connect(self):
        self.is_agent = 'agent=true' in self.scope.get('query_string', b'').decode()
        self.agent_id = self.scope.get('url_route', {}).get('kwargs', {}).get('agent_id')
        
        if not self.is_agent:
            await self.close()
            return
        
        # Join agent notification group
        await self.channel_layer.group_add('notifications_agent', self.channel_name)
        await self.accept()
        
        # Send initial dashboard data
        await self.send_dashboard_summary()
        
        # Set agent online status
        if self.agent_id:
            status_key = f"agent_online:{self.agent_id}"
            redis_client.setex(status_key, 3600, datetime.utcnow().isoformat())

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard('notifications_agent', self.channel_name)
        
        # Set agent offline status
        if hasattr(self, 'agent_id') and self.agent_id:
            status_key = f"agent_online:{self.agent_id}"
            redis_client.delete(status_key)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            
            if data.get('action') == 'get_dashboard_summary':
                await self.send_dashboard_summary()
            elif data.get('action') == 'heartbeat':
                # Update agent online status
                if self.agent_id:
                    status_key = f"agent_online:{self.agent_id}"
                    redis_client.setex(status_key, 3600, datetime.utcnow().isoformat())
                    
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON decode error in NotificationConsumer: {e}")

    async def send_dashboard_summary(self):
        """Send dashboard summary with overall statistics"""
        try:
            room_collection = await sync_to_async(get_room_collection)()
            contact_collection = await sync_to_async(get_contact_collection)()
            
            # Get total active rooms
            total_rooms = await sync_to_async(lambda: room_collection.count_documents({'is_active': True}))()
            
            # Get total unread messages across all rooms
            total_unread = 0
            rooms_with_unread = 0
            
            rooms = await sync_to_async(lambda: list(
                room_collection.find({'is_active': True}, {'room_id': 1})
            ))()
            
            for room in rooms:
                room_id = room['room_id']
                unread_key = f'unread:{room_id}'
                unread_count = int(redis_client.get(unread_key) or 0)
                total_unread += unread_count
                if unread_count > 0:
                    rooms_with_unread += 1
            
            # Get total contacts today
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            contacts_today = await sync_to_async(lambda: contact_collection.count_documents({
                'timestamp': {'$gte': today}
            }))()
            
            # Get online agents count
            online_agents = len([key for key in redis_client.keys('agent_online:*')])
            
            await self.send(text_data=json.dumps({
                'type': 'dashboard_summary',
                'data': {
                    'total_rooms': total_rooms,
                    'total_unread': total_unread,
                    'rooms_with_unread': rooms_with_unread,
                    'contacts_today': contacts_today,
                    'online_agents': online_agents,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }))
            
        except Exception as e:
            print(f"[ERROR] Error sending dashboard summary: {e}")

    async def notify(self, event):
        """Handle dashboard notifications"""
        event_type = event.get('event_type')
        payload = event.get('payload', {})
        
        try:
            if event_type in ['new_message_agent', 'unread_update', 'new_contact', 'new_room']:
                # Send updated dashboard summary for these events
                await self.send_dashboard_summary()
                
            # Forward specific notifications
            await self.send(text_data=json.dumps({
                'type': f'dashboard_{event_type}',
                'payload': payload,
                'timestamp': datetime.utcnow().isoformat()
            }))
            
        except Exception as e:
            print(f"[ERROR] Error in dashboard notify: {e}")


# Redis utility functions for notification management

def get_agent_notification_preferences(agent_id):
    """Get agent notification preferences from Redis"""
    pref_key = f"agent_prefs:{agent_id}"
    prefs = redis_client.get(pref_key)
    if prefs:
        return json.loads(prefs)
    
    # Default preferences
    default_prefs = {
        'new_messages': True,
        'new_contacts': True,
        'room_updates': True,
        'sound_notifications': True,
        'desktop_notifications': True
    }
    redis_client.setex(pref_key, 86400, json.dumps(default_prefs))  # 24 hours
    return default_prefs

def set_agent_notification_preferences(agent_id, preferences):
    """Set agent notification preferences in Redis"""
    pref_key = f"agent_prefs:{agent_id}"
    redis_client.setex(pref_key, 86400, json.dumps(preferences))

def get_unread_summary():
    """Get summary of unread messages across all rooms"""
    room_collection = get_room_collection()
    rooms = list(room_collection.find({'is_active': True}, {'room_id': 1}))
    
    unread_summary = {
        'total_unread': 0,
        'rooms_with_unread': 0,
        'room_details': []
    }
    
    for room in rooms:
        room_id = room['room_id']
        unread_key = f'unread:{room_id}'
        unread_count = int(redis_client.get(unread_key) or 0)
        
        if unread_count > 0:
            unread_summary['total_unread'] += unread_count
            unread_summary['rooms_with_unread'] += 1
            unread_summary['room_details'].append({
                'room_id': room_id,
                'unread_count': unread_count
            })
    
    return unread_summary