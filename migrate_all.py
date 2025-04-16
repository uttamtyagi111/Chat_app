import logging
from datetime import datetime
from utils.redis_client import redis_client
from wish_bot.db import get_chat_collection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)

def migrate_redis_to_mongo():
    """Migrate all messages from Redis to MongoDB in batches."""
    collection = get_chat_collection()
    batch_size = 1000  # Adjust based on your system
    batch = []
    skipped = 0
    migrated = 0

    try:
        # Ensure unique index on message_id to prevent duplicates
        collection.create_index('message_id', unique=True)
        logging.info("Ensured unique index on message_id")

        # Fetch all Redis keys
        keys = redis_client.keys('message:*')
        logging.info(f"Found {len(keys)} messages in Redis")

        for key in keys:
            try:
                # Get message data from Redis
                data = redis_client.hgetall(key)
                # Decode bytes to strings
                decoded_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in data.items()}

                # Prepare MongoDB document
                doc = {
                    'message_id': decoded_data.get('message_id', decoded_data.get('id', '')),
                    'room_id': decoded_data.get('room_id', 'default_room'),
                    'sender': decoded_data.get('sender', 'anonymous'),
                    'message': decoded_data.get('message', ''),
                    'file_url': decoded_data.get('file_url', ''),
                    'file_name': decoded_data.get('file_name', ''),
                    'delivered': decoded_data.get('delivered', 'true') == 'true',
                    'seen': decoded_data.get('seen', 'false') == 'true',
                    'timestamp': (datetime.fromisoformat(decoded_data['timestamp'])
                                 if decoded_data.get('timestamp')
                                 else datetime.now()),
                    'seen_at': (datetime.fromisoformat(decoded_data['seen_at'])
                               if decoded_data.get('seen_at')
                               else None)
                }
                batch.append(doc)

                # Insert batch when it reaches batch_size
                if len(batch) >= batch_size:
                    try:
                        collection.insert_many(batch, ordered=False)
                        migrated += len(batch)
                        logging.info(f"Migrated {len(batch)} messages (Total: {migrated})")
                        batch = []
                    except Exception as e:
                        logging.error(f"Error inserting batch: {e}")
                        # Optionally, log problematic documents for review
                        skipped += len(batch)
                        batch = []

            except (ValueError, KeyError) as e:
                logging.warning(f"Skipping message {decoded_data.get('message_id', 'unknown')}: {e}")
                skipped += 1
                continue
            except Exception as e:
                logging.error(f"Error processing key {key.decode('utf-8')}: {e}")
                skipped += 1
                continue

        # Insert any remaining messages
        if batch:
            try:
                collection.insert_many(batch, ordered=False)
                migrated += len(batch)
                logging.info(f"Migrated final {len(batch)} messages (Total: {migrated})")
            except Exception as e:
                logging.error(f"Error inserting final batch: {e}")
                skipped += len(batch)

        # Log summary
        logging.info(f"Migration complete! Migrated: {migrated}, Skipped: {skipped}")
        
        # Validate counts
        mongo_count = collection.count_documents({})
        logging.info(f"Total documents in MongoDB: {mongo_count}")
        if migrated + skipped != len(keys):
            logging.warning("Mismatch in counts. Check skipped messages in log.")

    except Exception as e:
        logging.error(f"Fatal error during migration: {e}")
        raise

def main():
    """Run the Redis-to-MongoDB migration."""
    logging.info("Starting Redis-to-MongoDB migration...")
    try:
        migrate_redis_to_mongo()
        logging.info("Migration completed successfully!")
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        raise

if __name__ == '__main__':
    main()