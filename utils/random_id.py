
import random
import string
from datetime import datetime
import uuid
import base64

def generate_room_id():
    """
    Generate a 32-character room ID by concatenating Base64-encoded UUIDs.
    """
    # One UUID produces 22 chars after Base64 encoding (16 bytes -> 24 chars - 2 padding chars)
    # To get 32 chars, we need one UUID (22 chars) plus part of another UUID (10 more chars)
    result = ""
    while len(result) < 32:
        uid = uuid.uuid4()
        encoded = base64.urlsafe_b64encode(uid.bytes).rstrip(b'=').decode('ascii')
        result += encoded
    return result[:32]

def generate_widget_id():
    """
    Generate a 14-character widget ID in the format xxxxxxxx-xxxx using UUID.
    """
    # Generate a UUID and convert to hex (32 chars without hyphens)
    uuid_str = str(uuid.uuid4()).replace('-', '')  # e.g., 550e8400e29b41d4a716446655440000
    # Format as xxxxxxxx-xxxx (first 8 chars, hyphen, next 4 chars)
    return f"{uuid_str[:8]}-{uuid_str[8:12]}"


def generate_contact_id():
    date_str = datetime.utcnow().strftime('%Y%m%d')
    rand_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"CONT-{date_str}-{rand_str}"