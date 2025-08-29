import json
import uuid
import datetime
import asyncio
from channels.layers import get_channel_layer
from channels.generic.websocket import AsyncWebsocketConsumer
from wish_bot.db import (
    get_chat_collection,
    get_room_collection,
    get_shortcut_collection,
    get_trigger_collection,
    insert_with_timestamps,
    get_contact_collection,
    get_admin_collection,
    get_widget_collection,
)
from utils.redis_client import redis_client
from asgiref.sync import sync_to_async
from utils.random_id import generate_room_id, generate_contact_id
import logging
from prometheus_client import Histogram

# Prometheus metrics for monitoring
message_delivery_time = Histogram('message_delivery_seconds', 'Time to deliver messages')
typing_event_time = Histogram('typing_event_seconds', 'Time to process typing events')
chat_history_time = Histogram('chat_history_seconds', 'Time to fetch chat history')
notification_time = Histogram('notification_delivery_seconds', 'Time to deliver notifications')

logger = logging.getLogger(__name__)

def get_notifier():
    return get_channel_layer()

async def get_agent_widgets(admin_id):
    """Get widgets assigned to an agent - Cached in Redis"""
    cache_key = f"agent_widgets:{admin_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    try:
        admin_collection = await sync_to_async(get_admin_collection)()
        agent_doc = await sync_to_async(lambda: admin_collection.find_one({'admin_id': admin_id}))()
        widgets = agent_doc.get('assigned_widgets', []) if agent_doc else []
        redis_client.setex(cache_key, 300, json.dumps(widgets))  # Cache for 5 minutes
        return widgets
    except Exception as e:
        logger.error(f"Error getting agent widgets for {admin_id}: {e}")
        return []

async def get_room_widget(room_id):
    """Get widget_id for a room - Cached in Redis"""
    cache_key = f"room_widget:{room_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return cached  # Already a string

    try:
        room_collection = await sync_to_async(get_room_collection)()
        room = await sync_to_async(lambda: room_collection.find_one({'room_id': room_id}))()
        widget_id = room.get('widget_id') if room else None
        if widget_id:
            redis_client.setex(cache_key, 3600, widget_id)  # Cache for 1 hour
        return widget_id
    except Exception as e:
        logger.error(f"Error getting room widget for {room_id}: {e}")
        return None

async def get_all_widget_ids():
    """Get all widget IDs - Cached in Redis"""
    cache_key = "all_widgets"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    collection = get_widget_collection()
    widgets = await sync_to_async(lambda: list(collection.find({}, {'widget_id': 1})))()
    widget_ids = [w['widget_id'] for w in widgets if 'widget_id' in w]
    redis_client.setex(cache_key, 300, json.dumps(widget_ids))  # Cache for 5 minutes
    return widget_ids

async def is_user_superadmin(admin_id):
    """Check if user is superadmin - Cached in Redis"""
    cache_key = f"superadmin:{admin_id}"
    cached = redis_client.get(cache_key)
    if cached:
        return cached == 'true'  # Direct string comparison

    collection = get_admin_collection()
    doc = await sync_to_async(lambda: collection.find_one({'admin_id': admin_id}))()
    is_super = doc and doc.get('role') == 'superadmin'
    redis_client.setex(cache_key, 300, 'true' if is_super else 'false')  # Cache for 5 minutes
    return is_super

async def notify_event(event_type, payload):
    """Send notifications to widget-specific Redis pub/sub channel"""
    with notification_time.time():
        try:
            channel_layer = get_channel_layer()
            widget_id = payload.get('widget_id')
            if not widget_id:
                logger.warning(f"notify_event - Missing widget_id in payload: {payload}")
                return

            await channel_layer.group_send(
                f'widget_notifications_{widget_id}',
                {
                    'type': 'notify_filtered',
                    'event_type': event_type,
                    'payload': payload,
                }
            )
            logger.debug(f"Sent {event_type} notification to widget {widget_id} channel")
        except Exception as e:
            logger.error(f"notify_event error: {e}", exc_info=True)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_name}'
        self.is_agent = 'agent=true' in self.scope.get('query_string', b'').decode()
        self.user = f'user_{str(uuid.uuid4())}' if not self.is_agent else 'Agent'
        self.admin_id = self.scope.get('url_route', {}).get('kwargs', {}).get('admin_id') if self.is_agent else None

        logger.debug(f"Connection attempt - Room: {self.room_name}, Is Agent: {self.is_agent}, User: {self.user}, Agent ID: {self.admin_id}")

        room_valid = await sync_to_async(self.validate_room)()
        if not room_valid:
            logger.debug(f"Room {self.room_name} is not valid, closing connection")
            await self.close()
            return

        # Get agent's assigned widgets (cached)
        if self.is_agent and self.admin_id:
            self.agent_widgets = await get_agent_widgets(self.admin_id)
            logger.debug(f"Agent {self.admin_id} assigned widgets: {self.agent_widgets}")
        else:
            self.agent_widgets = []

        if self.is_agent:
            room_widget_id = await sync_to_async(self.get_widget_id_from_room)()
            if not self.can_access_room(room_widget_id):
                logger.debug(f"Agent {self.admin_id} cannot access room {self.room_name}")
                await self.close()
                return

        # Set room active status for users
        if not self.is_agent:
            await self.set_room_active_status(self.room_name, True)

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        # Set agent online status
        if self.is_agent:
            await self.set_agent_online_status(True)

        await self.accept()
        logger.debug(f"WebSocket connection accepted for room: {self.room_name}")

        if not self.is_agent:
            self.widget_id = await sync_to_async(self.get_widget_id_from_room)()
            connection_timestamp = datetime.datetime.utcnow()
            redis_client.setex(f"live_visitor:{self.room_name}", 3600, connection_timestamp.isoformat())

            await notify_event('new_live_visitor', {
                'room_id': self.room_name,
                'widget_id': self.widget_id,
                'connection_timestamp': connection_timestamp.isoformat(),
                'visitor_id': self.user,
                'visitor_type': 'connected',
            })

            await notify_event('room_list_update', {
                'room_id': self.room_name,
                'widget_id': self.widget_id,
                'action': 'visitor_connected',
                'connection_timestamp': connection_timestamp.isoformat(),
            })

            self.triggers = await self.fetch_triggers_for_widget(self.widget_id)
            redis_client.set(f"predefined:{self.room_name}:{self.user}", 0)
            await self.send_trigger_message(0)
        else:
            await self.send_chat_history()
            await self.send_room_list()

    def validate_room(self):
        try:
            room_collection = get_room_collection()
            room = room_collection.find_one({'room_id': self.room_name})
            if room is None:
                logger.debug(f"Room {self.room_name} not found in database")
                return False
            return room.get('is_active', False)
        except Exception as e:
            logger.error(f"Error validating room {self.room_name}: {e}")
            return False

    def get_widget_id_from_room(self):
        cache_key = f"room_widget:{self.room_name}"
        cached = redis_client.get(cache_key)
        if cached:
            return cached

        try:
            room_collection = get_room_collection()
            room = room_collection.find_one({'room_id': self.room_name})
            widget_id = room.get('widget_id') if room else None
            if widget_id:
                redis_client.setex(cache_key, 3600, widget_id)
            return widget_id
        except Exception as e:
            logger.error(f"Error getting widget ID for {self.room_name}: {e}")
            return None

    def can_access_room(self, room_widget_id):
        if not self.is_agent or not self.admin_id:
            return True
        if not room_widget_id:
            return False
        return room_widget_id in self.agent_widgets

    async def set_agent_online_status(self, is_online):
        try:
            if self.is_agent and self.admin_id:
                status_key = f"agent_online:{self.admin_id}"
                count_key = f"agent_conn_count:{self.admin_id}"
                if is_online:
                    redis_client.incr(count_key)
                    redis_client.setex(status_key, 3600, datetime.datetime.utcnow().isoformat())
                else:
                    count = redis_client.decr(count_key)
                    if count <= 0:
                        redis_client.delete(status_key)
                        redis_client.delete(count_key)
        except Exception as e:
            logger.error(f"Error setting agent online status for {self.admin_id}: {e}")

    async def fetch_triggers_for_widget(self, widget_id):
        if not widget_id:
            logger.debug("No widget_id provided, cannot fetch triggers")
            return []

        cache_key = f"triggers:{widget_id}"
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)

        try:
            collection = await sync_to_async(get_trigger_collection)()
            triggers = await sync_to_async(lambda: list(
                collection.find({'widget_id': widget_id, 'is_active': True}).sort('order', 1)
            ))()
            redis_client.setex(cache_key, 300, json.dumps(triggers))
            return triggers
        except Exception as e:
            logger.error(f"Error fetching triggers for widget {widget_id}: {e}")
            return []

    async def send_trigger_message(self, index):
        try:
            if self.is_agent:
                return
            if not hasattr(self, 'triggers') or not self.triggers or index >= len(self.triggers):
                return

            trigger = self.triggers[index]
            message = trigger.get('message')
            suggested_replies = trigger.get('suggested_replies', [])
            timestamp = datetime.datetime.utcnow()
            message_id = generate_room_id()

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

            collection = await sync_to_async(get_chat_collection)()
            await sync_to_async(insert_with_timestamps)(collection, doc)

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
        except Exception as e:
            logger.error(f"Error in send_trigger_message: {e}", exc_info=True)

    async def disconnect(self, close_code):
        try:
            if hasattr(self, 'room_name'):
                disconnect_timestamp = datetime.datetime.utcnow()
                if not self.is_agent:
                    redis_client.delete(f'live_visitor:{self.room_name}')
                    widget_id = getattr(self, 'widget_id', None) or await sync_to_async(self.get_widget_id_from_room)()
                    if widget_id:
                        await notify_event('visitor_disconnected', {
                            'room_id': self.room_name,
                            'widget_id': widget_id,
                            'disconnect_timestamp': disconnect_timestamp.isoformat(),
                            'visitor_id': self.user,
                            'close_code': close_code,
                        })
                        await notify_event('room_list_update', {
                            'room_id': self.room_name,
                            'widget_id': widget_id,
                            'action': 'visitor_disconnected',
                            'disconnect_timestamp': disconnect_timestamp.isoformat(),
                        })

                if self.is_agent:
                    await self.set_agent_online_status(False)

                redis_client.delete(f'typing:{self.room_name}:{self.user}')
                if not self.is_agent:
                    redis_client.delete(f'predefined:{self.room_name}:{self.user}')

                await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        except Exception as e:
            logger.error(f"Error in disconnect: {e}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            collection = await sync_to_async(get_chat_collection)()

            if data.get('action') == 'get_room_list' and self.is_agent:
                await self.send_room_list()
                return

            if data.get('action') == 'heartbeat' and self.is_agent:
                await self.set_agent_online_status(True)
                return

            if data.get('action') == 'mark_room_read' and self.is_agent:
                await self.mark_room_messages_read(data.get('room_id', self.room_name))
                return

            if not self.is_agent and (data.get('message') or data.get('file_url') or data.get('form_data')):
                rate_limit_key = f"rate_limit:{self.user}"
                current_time = datetime.datetime.utcnow()
                last_message_time = redis_client.get(rate_limit_key)
                if last_message_time:
                    try:
                        last_message_time = datetime.datetime.fromisoformat(last_message_time)
                        if (current_time - last_message_time) < datetime.timedelta(seconds=1):
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
            logger.error(f"JSON decode error: {e}")
            await self.send(text_data=json.dumps({'error': 'Invalid message format'}))
        except Exception as e:
            logger.error(f"Error in receive: {e}", exc_info=True)

    async def mark_room_messages_read(self, room_id):
        try:
            room_widget_id = await get_room_widget(room_id)
            if not self.can_access_room(room_widget_id):
                return

            collection = await sync_to_async(get_chat_collection)()
            await sync_to_async(collection.update_many)(
                {'room_id': room_id, 'seen': False, 'sender': {'$ne': 'agent'}},
                {'$set': {'seen': True, 'seen_at': datetime.datetime.utcnow()}}
            )

            unread_key = f'unread:{room_id}'
            redis_client.delete(unread_key)

            await notify_event('unread_update', {
                'room_id': room_id,
                'widget_id': room_widget_id,
                'unread_count': 0,
                'timestamp': datetime.datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Error marking room messages as read: {e}")

    async def handle_typing(self, data):
        with typing_event_time.time():
            typing = data.get('typing', False)
            content = data.get('content', '')
            typing_key = f'typing:{self.room_name}:{self.user}'

            last_sent = redis_client.get(f"{typing_key}:last_sent")
            if last_sent and (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(last_sent)).total_seconds() < 1:
                return

            if typing:
                redis_client.setex(typing_key, 10, content)
                redis_client.setex(f"{typing_key}:last_sent", 10, datetime.datetime.utcnow().isoformat())
            else:
                redis_client.delete(typing_key)
                redis_client.delete(f"{typing_key}:last_sent")

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
        try:
            message_id = data.get('message_id')
            sender = data.get('sender', self.user)
            if not message_id:
                return

            result = await sync_to_async(collection.update_one)(
                {'message_id': message_id, 'room_id': self.room_name},
                {'$set': {'seen': True, 'seen_at': datetime.datetime.utcnow()}}
            )

            if self.is_agent and result.modified_count > 0:
                unread_key = f'unread:{self.room_name}'
                current_unread = int(redis_client.get(unread_key) or 0)
                if current_unread > 0:
                    new_unread = max(0, current_unread - 1)
                    if new_unread == 0:
                        redis_client.delete(unread_key)
                    else:
                        redis_client.set(unread_key, new_unread)

                    room_widget_id = await get_room_widget(self.room_name)
                    await notify_event('unread_update', {
                        'room_id': self.room_name,
                        'widget_id': room_widget_id,
                        'unread_count': new_unread,
                        'timestamp': datetime.datetime.utcnow().isoformat()
                    })

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'message_seen',
                    'message_id': message_id,
                    'sender': sender,
                    'timestamp': datetime.datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Error updating seen status: {e}")

    async def handle_form_data(self, data, collection):
        try:
            form_data = data.get('form_data', {})
            message_id = data.get('message_id') or generate_room_id()
            timestamp = datetime.datetime.utcnow()
            name = form_data.get('name', '')
            email = form_data.get('email', '')
            phone = form_data.get('phone', '')

            contact_collection = await sync_to_async(get_contact_collection)()
            room_collection = await sync_to_async(get_room_collection)()
            room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
            contact_id = room.get('contact_id') if room and room.get('contact_id') else generate_contact_id()
            widget_id = room.get('widget_id') if room else None

            contact_doc = {
                'contact_id': contact_id,
                'room_id': self.room_name,
                'name': name,
                'email': email,
                'phone': phone,
                'widget_id': widget_id,
                'timestamp': timestamp
            }
            await sync_to_async(insert_with_timestamps)(contact_collection, contact_doc)

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

            if not self.is_agent:
                unread_key = f'unread:{self.room_name}'
                new_unread_count = redis_client.incr(unread_key)
                await notify_event('unread_update', {
                    'room_id': self.room_name,
                    'widget_id': widget_id,
                    'unread_count': new_unread_count,
                    'timestamp': timestamp.isoformat()
                })

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
        except Exception as e:
            logger.error(f"Error handling form data: {e}")
            await self.send(text_data=json.dumps({'error': 'Failed to submit form data'}))

    async def handle_new_message(self, data, collection):
        with message_delivery_time.time():
            try:
                from bson import ObjectId
                timestamp = datetime.datetime.utcnow()
                timestamp_iso = timestamp.isoformat()
                message_id = data.get('message_id') or generate_room_id()
                contact_id = data.get('contact_id')
                sender = data.get('sender', self.user)
                shortcut_id = data.get('shortcut_id')
                file_url = data.get('file_url', '')
                file_name = data.get('file_name', '')
                display_sender_name = sender

                room_collection = await sync_to_async(get_room_collection)()
                room = await sync_to_async(lambda: room_collection.find_one({'room_id': self.room_name}))()
                if not room:
                    logger.error(f"Room {self.room_name} not found")
                    return None

                if not contact_id:
                    contact_id = room.get('contact_id') or generate_contact_id()

                widget_id = room.get('widget_id')
                assigned_admin_id = room.get('assigned_agent')

                if sender == 'agent':
                    display_sender_name = 'Agent'
                    if assigned_admin_id:
                        admin_collection = await sync_to_async(get_admin_collection)()
                        agent_doc = await sync_to_async(lambda: admin_collection.find_one({'admin_id': assigned_admin_id}))()
                        if agent_doc:
                            display_sender_name = agent_doc.get('name') or 'Agent'

                shortcut_doc = None
                suggested_replies = []
                is_shortcut = False

                if shortcut_id:
                    shortcut_collection = await sync_to_async(get_shortcut_collection)()
                    shortcut_doc = await sync_to_async(lambda: shortcut_collection.find_one({'shortcut_id': shortcut_id}))()
                    if shortcut_doc:
                        message = shortcut_doc.get('content', '')
                        suggested_replies = shortcut_doc.get('suggested_messages', [])
                        is_shortcut = True
                    else:
                        message = data.get('message', '')
                else:
                    message = data.get('message', '')

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
                    'timestamp': timestamp_iso,
                    'is_shortcut': is_shortcut,
                    'shortcut_id': shortcut_id if is_shortcut else None,
                    'suggested_replies': suggested_replies
                }

                await sync_to_async(insert_with_timestamps)(collection, doc)

                for k, v in doc.items():
                    if isinstance(v, datetime.datetime):
                        doc[k] = v.isoformat()
                    elif isinstance(v, ObjectId):
                        doc[k] = str(v)

                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'room_id': self.room_name,
                        'message': message,
                        'contact_id': contact_id,
                        'sender': display_sender_name,
                        'message_id': message_id,
                        'file_url': file_url,
                        'file_name': file_name,
                        'timestamp': timestamp_iso,
                        'suggested_replies': suggested_replies
                    }
                )

                if not self.is_agent:
                    unread_key = f'unread:{self.room_name}'
                    unread_count = redis_client.incr(unread_key)

                    notify_data = {
                        'room_id': self.room_name,
                        'widget_id': widget_id,
                        'message': doc,
                        'unread_count': unread_count,
                        'timestamp': timestamp_iso,
                        'sender_type': 'user'
                    }

                    await notify_event('new_message_agent', notify_data)
                    await notify_event('unread_update', {
                        'room_id': self.room_name,
                        'widget_id': widget_id,
                        'unread_count': unread_count,
                        'timestamp': timestamp_iso,
                    })
                    await notify_event('room_list_update', {
                        'room_id': self.room_name,
                        'widget_id': widget_id,
                        'action': 'new_message',
                        'timestamp': timestamp_iso,
                    })

                    redis_key = f"predefined:{self.room_name}:{self.user}"
                    current_index = int(redis_client.get(redis_key) or 0)
                    next_index = current_index + 1
                    if hasattr(self, 'triggers') and self.triggers and next_index < len(self.triggers):
                        redis_client.set(redis_key, next_index)
                        await asyncio.sleep(0.5)
                        await self.send_trigger_message(next_index)
                        if next_index == 1:
                            await self.send_show_form_signal()

                return {
                    'room_id': self.room_name,
                    'widget_id': widget_id,
                    'message': message,
                    'file_url': file_url,
                    'file_name': file_name,
                    'message_id': message_id,
                    'contact_id': contact_id,
                    'sender': display_sender_name,
                    'timestamp': timestamp_iso,
                    'suggested_replies': suggested_replies
                }
            except Exception as e:
                logger.error(f"Error in handle_new_message: {e}", exc_info=True)
                return None

    async def cache_room_history(self, room_id):
        try:
            collection = await sync_to_async(get_chat_collection)()
            messages = await sync_to_async(lambda: list(
                collection.find({'room_id': room_id}, {'_id': 0}).sort('timestamp', -1).limit(50)
            ))()
            redis_client.setex(f"chat_history:{room_id}", 300, json.dumps(messages))
            return messages
        except Exception as e:
            logger.error(f"Error caching room history for {room_id}: {e}")
            return []

    async def send_chat_history(self):
        with chat_history_time.time():
            try:
                room_widget_id = await get_room_widget(self.room_name)
                if not self.can_access_room(room_widget_id):
                    await self.send(text_data=json.dumps({'error': 'Access denied to this room'}))
                    return

                cache_key = f"chat_history:{self.room_name}"
                cached = redis_client.get(cache_key)
                if cached:
                    messages = json.loads(cached)
                else:
                    messages = await self.cache_room_history(self.room_name)

                for msg in messages:
                    if isinstance(msg.get('timestamp'), str):
                        msg['timestamp'] = msg['timestamp']
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
                logger.error(f"Error sending chat history: {e}")

    async def send_room_list(self):
        try:
            cache_key = f"room_list:{self.admin_id}"
            cached = redis_client.get(cache_key)
            if cached:
                await self.send(text_data=cached)
                return

            room_collection = await sync_to_async(get_room_collection)()
            chat_collection = await sync_to_async(get_chat_collection)()
            contact_collection = await sync_to_async(get_contact_collection)()

            if self.is_agent and self.agent_widgets:
                rooms = await sync_to_async(lambda: list(
                    room_collection.find({'is_active': True, 'widget_id': {'$in': self.agent_widgets}})
                ))()
            else:
                rooms = await sync_to_async(lambda: list(
                    room_collection.find({'is_active': True})
                ))()

            room_list = []
            total_unread = 0

            for room in rooms:
                room_id = room['room_id']
                assigned_agent = room.get('assigned_agent')
                if self.is_agent and assigned_agent and assigned_agent not in [None, 'agent', 'superadmin', self.admin_id]:
                    continue

                last_message = await sync_to_async(lambda: chat_collection.find_one(
                    {'room_id': room_id}, sort=[('timestamp', -1)]
                ))()
                contact_doc = await sync_to_async(lambda: contact_collection.find_one({'room_id': room_id}))()
                unread_key = f'unread:{room_id}'
                unread_count = int(redis_client.get(unread_key) or 0)
                total_unread += unread_count

                timestamp = last_message.get('timestamp') if last_message else None
                timestamp_str = timestamp if isinstance(timestamp, str) else (timestamp.isoformat() if isinstance(timestamp, datetime.datetime) else '')

                room_list.append({
                    'room_id': room_id,
                    'widget_id': room.get('widget_id'),
                    'contact': {
                        'name': contact_doc.get('name') if contact_doc else '',
                        'email': contact_doc.get('email') if contact_doc else '',
                        'phone': contact_doc.get('phone') if contact_doc else ''
                    },
                    'latest_message': last_message.get('message') if last_message else '',
                    'latest_message_sender': last_message.get('sender') if last_message else '',
                    'timestamp': timestamp_str,
                    'unread_count': unread_count,
                    'has_unread': unread_count > 0,
                    'assigned_agent': assigned_agent
                })

            room_list.sort(key=lambda x: x['timestamp'], reverse=True)

            response = json.dumps({
                'type': 'room_list',
                'rooms': room_list,
                'total_unread': total_unread,
                'agent_widgets': self.agent_widgets if self.is_agent else [],
                'timestamp': datetime.datetime.utcnow().isoformat()
            })

            redis_client.setex(cache_key, 60, response)
            await self.send(text_data=response)
        except Exception as e:
            logger.error(f"Error sending room list: {e}")

    async def send_show_form_signal(self):
        try:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'show_form_signal',
                    'show_form': True,
                    'form_type': 'contact'
                }
            )
        except Exception as e:
            logger.error(f"Error sending show form signal: {e}")

    async def chat_message(self, event):
        try:
            if event.get('room_id') != self.room_name:
                return
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
            logger.error(f"Error in chat_message: {e}")

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
            await self.send(text_data=json.dumps({
                'type': 'show_form_signal',
                'show_form': event['show_form'],
                'form_type': event['form_type']
            }))
        except Exception as e:
            logger.error(f"Error in show_form_signal: {e}")

    @sync_to_async
    def set_room_active_status(self, room_id, status: bool):
        try:
            collection = get_room_collection()
            result = collection.update_one(
                {'room_id': room_id},
                {'$set': {'is_active': status}},
                upsert=True
            )
            logger.debug(f"Room status update for {room_id}: {result.modified_count} modified")
        except Exception as e:
            logger.error(f"Error updating room status for {room_id}: {e}")

class NotificationConsumer(AsyncWebsocketConsumer):
    """Dedicated consumer for agent/superadmin dashboard notifications with widget filtering"""
    async def connect(self):
        self.admin_id = self.scope.get('url_route', {}).get('kwargs', {}).get('admin_id')
        self.query_string = self.scope.get('query_string', b'').decode()
        self.is_agent = 'agent=true' in self.query_string
        self.is_superadmin = await is_user_superadmin(self.admin_id)

        if not self.admin_id:
            await self.close()
            return

        if self.is_superadmin:
            self.agent_widgets = await get_all_widget_ids()
        else:
            self.agent_widgets = await get_agent_widgets(self.admin_id)

        logger.debug(f"NotificationConsumer - Admin {self.admin_id} widgets: {self.agent_widgets}")

        for widget_id in self.agent_widgets:
            await self.channel_layer.group_add(f'widget_notifications_{widget_id}', self.channel_name)

        await self.accept()
        await self.send_dashboard_summary()
        redis_client.setex(f"agent_online:{self.admin_id}", 3600, datetime.datetime.utcnow().isoformat())

    async def disconnect(self, close_code):
        try:
            for widget_id in self.agent_widgets:
                await self.channel_layer.group_discard(f'widget_notifications_{widget_id}', self.channel_name)
            if self.admin_id:
                redis_client.delete(f"agent_online:{self.admin_id}")
        except Exception as e:
            logger.error(f"Error in NotificationConsumer disconnect for admin {self.admin_id}: {e}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')

            if action == 'get_dashboard_summary':
                await self.send_dashboard_summary()
            elif action == 'heartbeat':
                redis_client.setex(f"agent_online:{self.admin_id}", 3600, datetime.datetime.utcnow().isoformat())
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat_response',
                    'timestamp': datetime.datetime.utcnow().isoformat()
                }))
            elif action == 'notify_event':
                event_type = data.get('event_type')
                payload = data.get('payload', {})
                await notify_event(event_type, payload)
            elif action == 'mark_messages_read':
                room_id = data.get('payload', {}).get('room_id')
                if room_id:
                    await self.mark_room_messages_read(room_id)

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in NotificationConsumer: {e}")
        except Exception as e:
            logger.error(f"Error in NotificationConsumer receive: {e}")

    async def mark_room_messages_read(self, room_id):
        try:
            unread_key = f'unread:{room_id}'
            redis_client.delete(unread_key)

            widget_id = await get_room_widget(room_id)
            if widget_id:
                await notify_event('unread_update', {
                    'room_id': room_id,
                    'widget_id': widget_id,
                    'unread_count': 0,
                    'timestamp': datetime.datetime.utcnow().isoformat()
                })

            logger.debug(f"Marked messages as read for room {room_id}")
        except Exception as e:
            logger.error(f"Error marking messages as read for room {room_id}: {e}")

    async def send_dashboard_summary(self):
        try:
            cache_key = f"dashboard_summary:{self.admin_id}"
            cached = redis_client.get(cache_key)
            if cached:
                await self.send(text_data=cached)
                logger.debug(f"Sent cached dashboard summary to admin {self.admin_id}")
                return

            room_collection = await sync_to_async(get_room_collection)()
            contact_collection = await sync_to_async(get_contact_collection)()

            widget_filter = {'widget_id': {'$in': self.agent_widgets}} if self.agent_widgets else {}
            rooms = await sync_to_async(lambda: list(room_collection.find({
                'is_active': True,
                **widget_filter
            }, {'room_id': 1, 'assigned_agent': 1, 'widget_id': 1})))()

            total_rooms = len(rooms)
            total_unread = 0
            rooms_with_unread = 0
            live_rooms = []
            assigned_rooms = []

            for room in rooms:
                room_id = room['room_id']
                assigned_agent = room.get('assigned_agent')
                unread = int(redis_client.get(f'unread:{room_id}') or 0)

                if self.is_superadmin or assigned_agent == self.admin_id or assigned_agent is None:
                    total_unread += unread
                    if unread > 0:
                        rooms_with_unread += 1

                if not assigned_agent:
                    live_rooms.append(room_id)
                elif assigned_agent == self.admin_id or self.is_superadmin:
                    assigned_rooms.append(room_id)

            today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            contacts_today = await sync_to_async(lambda: contact_collection.count_documents({
                'timestamp': {'$gte': today},
                **widget_filter
            }))()

            online_agents = len([key for key in redis_client.scan_iter('agent_online:*')])

            response = json.dumps({
                'type': 'dashboard_summary',
                'data': {
                    'total_rooms': total_rooms,
                    'total_unread': total_unread,
                    'rooms_with_unread': rooms_with_unread,
                    'contacts_today': contacts_today,
                    'online_agents': online_agents,
                    'live_visitors': len(live_rooms),
                    'assigned_rooms': len(assigned_rooms),
                    'live_room_ids': live_rooms,
                    'assigned_room_ids': assigned_rooms,
                    'agent_widgets': self.agent_widgets,
                    'timestamp': datetime.datetime.utcnow().isoformat()
                }
            })

            redis_client.setex(cache_key, 30, response)
            await self.send(text_data=response)
            logger.debug(f"Dashboard summary sent to admin {self.admin_id}")
        except Exception as e:
            logger.error(f"Error sending dashboard summary for admin {self.admin_id}: {e}")

    async def notify_filtered(self, event):
        try:
            event_type = event.get('event_type')
            payload = event.get('payload', {})
            widget_id = payload.get('widget_id')

            if event_type in ['new_message_agent', 'unread_update', 'new_contact', 'new_room', 'new_live_visitor']:
                redis_client.delete(f"dashboard_summary:{self.admin_id}")
                await self.send_dashboard_summary()

            await self.send(text_data=json.dumps({
                'type': f'dashboard_{event_type}',
                'payload': payload,
                'timestamp': datetime.datetime.utcnow().isoformat()
            }))
            logger.debug(f"Notification sent to admin {self.admin_id} for event {event_type}")
        except Exception as e:
            logger.error(f"Error in notify_filtered for admin {self.admin_id}: {e}")

def get_agent_notification_preferences(admin_id):
    """Get agent notification preferences from Redis"""
    pref_key = f"agent_prefs:{admin_id}"
    prefs = redis_client.get(pref_key)
    if prefs:
        return json.loads(prefs)

    default_prefs = {
        'new_messages': True,
        'new_contacts': True,
        'room_updates': True,
        'sound_notifications': True,
        'desktop_notifications': True,
        'widget_filter': True
    }
    redis_client.setex(pref_key, 86400, json.dumps(default_prefs))
    return default_prefs

def set_agent_notification_preferences(admin_id, preferences):
    """Set agent notification preferences in Redis"""
    pref_key = f"agent_prefs:{admin_id}"
    redis_client.setex(pref_key, 86400, json.dumps(preferences))

async def get_unread_summary_by_widget(widget_ids=None):
    """Get summary of unread messages filtered by widgets"""
    try:
        room_collection = await sync_to_async(get_room_collection)()
        widget_filter = {'widget_id': {'$in': widget_ids}} if widget_ids else {}

        rooms = await sync_to_async(lambda: list(
            room_collection.find({'is_active': True, **widget_filter}, {'room_id': 1, 'widget_id': 1})
        ))()

        unread_summary = {
            'total_unread': 0,
            'rooms_with_unread': 0,
            'room_details': [],
            'widget_breakdown': {}
        }

        pipe = redis_client.pipeline()
        for room in rooms:
            pipe.get(f'unread:{room["room_id"]}')
        unread_counts = pipe.execute()

        for idx, room in enumerate(rooms):
            room_id = room['room_id']
            room_widget_id = room.get('widget_id')
            unread_count = int(unread_counts[idx] or 0)

            if unread_count > 0:
                unread_summary['total_unread'] += unread_count
                unread_summary['rooms_with_unread'] += 1
                unread_summary['room_details'].append({
                    'room_id': room_id,
                    'widget_id': room_widget_id,
                    'unread_count': unread_count
                })

                if room_widget_id:
                    if room_widget_id not in unread_summary['widget_breakdown']:
                        unread_summary['widget_breakdown'][room_widget_id] = {
                            'unread_count': 0,
                            'rooms_count': 0
                        }
                    unread_summary['widget_breakdown'][room_widget_id]['unread_count'] += unread_count
                    unread_summary['widget_breakdown'][room_widget_id]['rooms_count'] += 1

        return unread_summary
    except Exception as e:
        logger.error(f"Error getting unread summary by widget: {e}")
        return {
            'total_unread': 0,
            'rooms_with_unread': 0,
            'room_details': [],
            'widget_breakdown': {}
        }

def get_agent_accessible_rooms(admin_id):
    """Get room IDs that an agent can access based on widget assignment"""
    try:
        admin_collection = get_admin_collection()
        agent_doc = admin_collection.find_one({'admin_id': admin_id})

        if not agent_doc:
            return []

        agent_widgets = agent_doc.get('assigned_widgets', [])
        if not agent_widgets:
            return []

        room_collection = get_room_collection()
        rooms = list(room_collection.find({
            'is_active': True,
            'widget_id': {'$in': agent_widgets}
        }, {'room_id': 1}))

        return [room['room_id'] for room in rooms]
    except Exception as e:
        logger.error(f"Error getting agent accessible rooms for {admin_id}: {e}")
        return []

def get_widget_statistics(widget_id):
    """Get comprehensive statistics for a specific widget"""
    try:
        room_collection = get_room_collection()
        contact_collection = get_contact_collection()
        chat_collection = get_chat_collection()

        active_rooms = list(room_collection.find({
            'widget_id': widget_id,
            'is_active': True
        }, {'room_id': 1}))

        room_ids = [room['room_id'] for room in active_rooms]

        pipe = redis_client.pipeline()
        for room_id in room_ids:
            pipe.get(f'unread:{room_id}')
        unread_counts = pipe.execute()
        total_unread = sum(int(count or 0) for count in unread_counts)

        total_contacts = contact_collection.count_documents({'widget_id': widget_id})

        yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        recent_messages = chat_collection.count_documents({
            'room_id': {'$in': room_ids},
            'timestamp': {'$gte': yesterday}
        })

        return {
            'widget_id': widget_id,
            'active_rooms': len(active_rooms),
            'total_unread': total_unread,
            'total_contacts': total_contacts,
            'recent_messages_24h': recent_messages,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting widget statistics for {widget_id}: {e}")
        return {
            'widget_id': widget_id,
            'active_rooms': 0,
            'total_unread': 0,
            'total_contacts': 0,
            'recent_messages_24h': 0,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }