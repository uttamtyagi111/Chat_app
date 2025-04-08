import random
import string

def generate_room_id(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
