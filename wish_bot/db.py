from dotenv import load_dotenv
import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime, timezone
import redis

load_dotenv()

# Singleton MongoClient
_mongo_client = None
_redis_client = None

def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        uri = os.getenv('MONGO_URI')
        if not uri:
            raise ValueError("MONGO_URI not set in environment variables")
        _mongo_client = MongoClient(uri, server_api=ServerApi('1'))
        try:
            _mongo_client.admin.command('ping')
            print("Connected to MongoDB Atlas!")
        except Exception as e:
            print(f"Connection error: {e}")
            _mongo_client = None
            raise
    return _mongo_client


def get_redis_client():
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv('REDIS_URL')
        try:
            if redis_url:
                # Use REDIS_URL (internal for Render, external for local)
                _redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to localhost for local development
                _redis_client = redis.StrictRedis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True
                )
            # Test the connection
            _redis_client.ping()
            print("Connected to Redis!")
        except redis.ConnectionError as e:
            print(f"Redis connection error: {e}")
            if "No such host" in str(e):
                print("Error: Redis hostname not found. Ensure REDIS_URL is correct and accessible (e.g., internal URL for Render, external URL for local).")
            elif "SSL" in str(e):
                print("Error: SSL/TLS issue. Ensure REDIS_URL uses 'rediss://' for external connections and your environment supports SSL.")
            _redis_client = None
            raise
        except redis.AuthenticationError as e:
            print(f"Redis authentication error: {e}")
            print("Error: Check username and password in REDIS_URL (e.g., rediss://username:password@host:port).")
            _redis_client = None
            raise
    return _redis_client

def find_duplicates(collection, field):
    duplicates = collection.aggregate([
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"count": {"$gt": 1}}}
    ])
    return list(duplicates)

def remove_duplicates(collection, field):
    duplicates = find_duplicates(collection, field)
    for doc in duplicates:
        ids_to_delete = doc["ids"][1:]
        collection.delete_many({"_id": {"$in": ids_to_delete}})
    print(f"Removed {len(duplicates)} duplicate {field} entries.")

def get_chat_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['messages']
    
    existing_indexes = collection.index_information()
    
    if 'message_id_1' in existing_indexes:
        if not existing_indexes['message_id_1'].get('unique', False):
            collection.drop_index('message_id_1')
            remove_duplicates(collection, 'message_id')
            collection.create_index([('message_id', 1)], unique=True, name='message_id_1')
    else:
        remove_duplicates(collection, 'message_id')
        collection.create_index([('message_id', 1)], unique=True, name='message_id_1')

    if 'room_id_1_timestamp_-1' not in existing_indexes:
        collection.create_index([('room_id', 1), ('timestamp', -1)], name='room_id_1_timestamp_-1')
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')
    
    return collection

def get_room_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['rooms']
    
    existing_indexes = collection.index_information()
    
    if 'room_id_1' in existing_indexes:
        if not existing_indexes['room_id_1'].get('unique', False):
            print("Dropping non-unique room_id_1 index...")
            collection.drop_index('room_id_1')
            remove_duplicates(collection, 'room_id')
            collection.create_index([('room_id', 1)], unique=True, name='room_id_1')
    else:
        remove_duplicates(collection, 'room_id')
        collection.create_index([('room_id', 1)], unique=True, name='room_id_1')

    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')
    
    return collection

def get_widget_collection():
    """
    Get MongoDB collection for widgets.
    """
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['widgets']
    
    existing_indexes = collection.index_information()
    
    # Ensure unique index on widget_id
    if 'widget_id_1' in existing_indexes:
        if not existing_indexes['widget_id_1'].get('unique', False):
            print("Dropping non-unique widget_id_1 index...")
            collection.drop_index('widget_id_1')
            remove_duplicates(collection, 'widget_id')
            collection.create_index([('widget_id', 1)], unique=True, name='widget_id_1')
    else:
        remove_duplicates(collection, 'widget_id')
        collection.create_index([('widget_id', 1)], unique=True, name='widget_id_1')

    # Add indexes for created_at and updated_at
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')
    
    return collection

def insert_with_timestamps(collection, document):
    """Insert a document with created_at and updated_at timestamps in UTC"""
    current_time = datetime.now(timezone.utc)
    document['created_at'] = current_time
    document['updated_at'] = current_time
    return collection.insert_one(document)

def update_with_timestamp(collection, query, update_data):
    """Update a document and update the updated_at timestamp in UTC"""
    if '$set' not in update_data:
        update_data['$set'] = {}
    
    update_data['$set']['updated_at'] = datetime.now(timezone.utc)
    return collection.update_one(query, update_data)

def update_many_with_timestamp(collection, query, update_data):
    """Update multiple documents and update the updated_at timestamp in UTC"""
    if '$set' not in update_data:
        update_data['$set'] = {}
    
    update_data['$set']['updated_at'] = datetime.now(timezone.utc)
    return collection.update_many(query, update_data)

def get_agent_notes_collection():
    """
    Get MongoDB collection for agent notes
    """
    client = get_mongo_client() 
    db = client['wish_bot_db'] 
    collection = db['agent_notes']  
    
    return collection

def get_ticket_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['tickets']
    
    # Create indexes you want on ticket_id, created_at, updated_at, status etc.
    existing_indexes = collection.index_information()
    
    if 'ticket_id_1' not in existing_indexes:
        collection.create_index([('ticket_id', 1)], unique=True, name='ticket_id_1')
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')
    
    return collection

# def get_contact_collection():
#     client = get_mongo_client()
#     db = client['wish_bot_db']
#     collection = db['contacts']

#     # Index on contact_id or email/phone for uniqueness
#     existing_indexes = collection.index_information()

#     if 'contact_id_1' not in existing_indexes:
#         collection.create_index([('contact_id', 1)], unique=True, name='contact_id_1')
#     if 'email_1' not in existing_indexes:
#         collection.create_index([('email', 1)], unique=True, name='email_1')
#     if 'created_at_-1' not in existing_indexes:
#         collection.create_index([('created_at', -1)], name='created_at_-1')
    
#     return collection

# Similarly for shortcuts, tags

def get_shortcut_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['shortcuts']

    existing_indexes = collection.index_information()

    # Create compound unique index on (title + widget_id)
    if 'title_widget_unique' not in existing_indexes:
        collection.create_index([('title', 1), ('widget_id', 1)], unique=True, name='title_widget_unique')

    if 'shortcut_id_1' not in existing_indexes:
        collection.create_index([('shortcut_id', 1)], unique=True, name='shortcut_id_1')

    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')

    return collection


    return collection

def get_tag_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['tags']

    existing_indexes = collection.index_information()

    # Remove global unique index on 'name'
    if 'name_1' in existing_indexes:
        collection.drop_index('name_1')

    # Create compound unique index on (name + widget_id)
    if 'name_widget_unique' not in existing_indexes:
        collection.create_index([('name', 1), ('widget_id', 1)], unique=True, name='name_widget_unique')

    if 'tag_id_1' not in existing_indexes:
        collection.create_index([('tag_id', 1)], unique=True, name='tag_id_1')

    return collection

    return collection

def get_user_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['users']

    existing_indexes = collection.index_information()

    if 'user_id_1' not in existing_indexes:
        collection.create_index([('user_id', 1)], unique=True, name='user_id_1')
    if 'email_1' not in existing_indexes:
        collection.create_index([('email', 1)], unique=True, name='email_1')

    return collection

# def get_agent_collection():
#     client = get_mongo_client()
#     db = client['wish_bot_db']
#     collection = db['agents']

#     existing_indexes = collection.index_information()
#     if 'agent_id_1' not in existing_indexes:
#         collection.create_index([('agent_id', 1)], unique=True, name='agent_id_1')
#     if 'email_1' not in existing_indexes:
#         collection.create_index([('email', 1)], unique=True, name='email_1')

#     return collection


def get_contact_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['contacts']

    existing_indexes = collection.index_information()

    # Ensure unique index on contact_id
    if 'contact_id_1' in existing_indexes:
        if not existing_indexes['contact_id_1'].get('unique', False):
            print("Dropping non-unique contact_id_1 index...")
            collection.drop_index('contact_id_1')
            remove_duplicates(collection, 'contact_id')
            collection.create_index([('contact_id', 1)], unique=True, name='contact_id_1')
    else:
        remove_duplicates(collection, 'contact_id')
        collection.create_index([('contact_id', 1)], unique=True, name='contact_id_1')

    # ✅ Unique index on email only
    if 'email_1' in existing_indexes:
        if not existing_indexes['email_1'].get('unique', False):
            collection.drop_index('email_1')
            remove_duplicates(collection, 'email')
            collection.create_index([('email', 1)], unique=True, name='email_1')
    else:
        remove_duplicates(collection, 'email')
        collection.create_index([('email', 1)], unique=True, name='email_1')

    # Optional index on name (non-unique, searchable)
    if 'name_1' not in existing_indexes:
        collection.create_index([('name', 1)], unique=False, name='name_1')

    # Timestamps
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')

    return collection


def get_agent_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['agents']  # Change this name if your agents collection is different

    existing_indexes = collection.index_information()

    # Ensure unique index on agent_id (assuming this is your unique field)
    if 'agent_id_1' in existing_indexes:
        if not existing_indexes['agent_id_1'].get('unique', False):
            print("Dropping non-unique agent_id_1 index...")
            collection.drop_index('agent_id_1')
            remove_duplicates(collection, 'agent_id')
            collection.create_index([('agent_id', 1)], unique=True, name='agent_id_1')
    else:
        remove_duplicates(collection, 'agent_id')
        collection.create_index([('agent_id', 1)], unique=True, name='agent_id_1')

    # Optional index on name or email
    if 'name_1' not in existing_indexes:
        collection.create_index([('name', 1)], name='name_1')

    if 'email_1' not in existing_indexes:
        collection.create_index([('email', 1)], name='email_1')

    # Timestamps (optional)
    if 'created_at_-1' not in existing_indexes:
        collection.create_index([('created_at', -1)], name='created_at_-1')
    if 'updated_at_-1' not in existing_indexes:
        collection.create_index([('updated_at', -1)], name='updated_at_-1')

    return collection



def get_trigger_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['triggers']

    # Create indexes for commonly used fields
    indexes = collection.index_information()

    if 'trigger_id_1' not in indexes:
        collection.create_index('trigger_id', unique=True)

    if 'name_1' not in indexes:
        collection.create_index('name')

    if 'is_active_1' not in indexes:
        collection.create_index('is_active')

    if 'tags_1' not in indexes:
        collection.create_index('tags')

    return collection

def get_knowledge_base_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['knowledge_base']

    # Create indexes for commonly used fields
    indexes = collection.index_information()

    if 'kb_id_1' not in indexes:
        collection.create_index('kb_id', unique=True)

    if 'title_1' not in indexes:
        collection.create_index('title')

    if 'tags_1' not in indexes:
        collection.create_index('tags')

    return collection



def get_admin_collection():
    """
    Get MongoDB collection for admin users.
    """
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['admins']

    existing_indexes = collection.index_information()

    # Ensure unique index on email
    if 'email_1' in existing_indexes:
        if not existing_indexes['email_1'].get('unique', False):
            print("Dropping non-unique email_1 index...")
            collection.drop_index('email_1')
            remove_duplicates(collection, 'email')
            collection.create_index([('email', 1)], unique=True, name='email_1')
    else:
        remove_duplicates(collection, 'email')
        collection.create_index([('email', 1)], unique=True, name='email_1')

    return collection


def get_blacklist_collection():
    """
    Get MongoDB collection for blacklisted tokens.
    """
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['blacklisted_tokens']

    existing_indexes = collection.index_information()

    # Ensure unique index on token
    if 'token_1' in existing_indexes:
        if not existing_indexes['token_1'].get('unique', False):
            print("Dropping non-unique token_1 index...")
            collection.drop_index('token_1')
            remove_duplicates(collection, 'token')
            collection.create_index([('token', 1)], unique=True, name='token_1')
    else:
        remove_duplicates(collection, 'token')
        collection.create_index([('token', 1)], unique=True, name='token_1')

    return collection