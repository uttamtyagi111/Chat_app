from dotenv import load_dotenv
import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime

load_dotenv()

def get_mongo_client():
    uri = os.getenv('MONGO_URI')
    if not uri:
        raise ValueError("MONGO_URI not set in environment variables")
    client = MongoClient(uri, server_api=ServerApi('1'))
    try:
        client.admin.command('ping')
        print("Connected to MongoDB Atlas!")
    except Exception as e:
        print(f"Connection error: {e}")
    return client

def get_chat_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['messages']
    
    # Create indexes
    collection.create_index([('room_id', 1), ('timestamp', -1)])
    collection.create_index([('message_id', 1)])
    collection.create_index([('created_at', -1)])
    collection.create_index([('updated_at', -1)])
    
    return collection

def get_room_collection():
    client = get_mongo_client()
    db = client['wish_bot_db']
    collection = db['rooms']
    
    # Create indexes
    collection.create_index([('room_id', 1)])
    collection.create_index([('created_at', -1)])
    collection.create_index([('updated_at', -1)])
    
    return collection

def insert_with_timestamps(collection, document):
    """Insert a document with created_at and updated_at timestamps"""
    current_time = datetime.now()
    document['created_at'] = current_time
    document['updated_at'] = current_time
    return collection.insert_one(document)

def update_with_timestamp(collection, query, update_data):
    """Update a document and update the updated_at timestamp"""
    if '$set' not in update_data:
        update_data['$set'] = {}
    
    update_data['$set']['updated_at'] = datetime.now()
    return collection.update_one(query, update_data)

def update_many_with_timestamp(collection, query, update_data):
    """Update multiple documents and update the updated_at timestamp for all"""
    if '$set' not in update_data:
        update_data['$set'] = {}
    
    update_data['$set']['updated_at'] = datetime.now()
    return collection.update_many(query, update_data)