from django.shortcuts import render, redirect
from django.utils import timezone
from bson import ObjectId
from wish_bot.db import get_ticket_collection,get_tag_collection, get_agent_collection
from wish_bot.db import get_shortcut_collection,get_trigger_collection

def ticket_list(request):
    tickets = list(get_ticket_collection().find())
    return render(request, 'support/ticket_list.html', {'tickets': tickets})

# Add ticket
def add_ticket(request):
    if request.method == 'POST':
        subject = request.POST.get('subject')
        description = request.POST.get('description')
        tags = request.POST.getlist('tags')
        priority = request.POST.get('priority')
        assigned_to = request.POST.get('assigned_to')

        get_ticket_collection().insert_one({
            'subject': subject,
            'description': description,
            'tags': tags,
            'priority': priority,
            'status': 'Open',
            'created_at': timezone.now(),
            'updated_at': timezone.now(),
            'assigned_to': ObjectId(assigned_to) if assigned_to else None
        })
        return redirect('ticket-list')

    tag_choices = list(get_tag_collection().find())
    agents = list(get_agent_collection().find())
    return render(request, 'support/add_ticket.html', {'tags': tag_choices, 'agents': agents})

# Edit ticket
def edit_ticket(request, ticket_id):
    ticket = get_ticket_collection().find_one({'_id': ObjectId(ticket_id)})
    if request.method == 'POST':
        get_ticket_collection().update_one({'_id': ObjectId(ticket_id)}, {
            '$set': {
                'subject': request.POST.get('subject'),
                'description': request.POST.get('description'),
                'tags': request.POST.getlist('tags'),
                'priority': request.POST.get('priority'),
                'status': request.POST.get('status'),
                'assigned_to': ObjectId(request.POST.get('assigned_to')) if request.POST.get('assigned_to') else None,
                'updated_at': timezone.now()
            }
        })
        return redirect('ticket-list')

    tag_choices = list(get_tag_collection().find())
    agents = list(get_agent_collection().find())
    return render(request, 'support/edit_ticket.html', {
        'ticket': ticket,
        'tags': tag_choices,
        'agents': agents
    })
# Delete ticket
def delete_ticket(request, ticket_id):
    get_ticket_collection().delete_one({'_id': ObjectId(ticket_id)})
    return redirect('ticket-list')

# List all shortcuts
def shortcut_list(request):
    shortcuts = list(get_shortcut_collection().find())
    for s in shortcuts:
        s['id'] = str(s['_id'])  # add 'id' as string of '_id'
    return render(request, 'support/shortcut_list.html', {'shortcuts': shortcuts})


import random
def get_random_color():
    colors = ['#FF5733', '#33FF57', '#3357FF', '#F39C12', '#9B59B6', '#1ABC9C']
    return random.choice(colors)



def add_shortcut(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        add_tags = request.POST.get('add_tags', '').split(',')
        remove_tags = request.POST.get('remove_tags', '').split(',')
        suggested_messages = request.POST.get('suggested_messages', '').split('\n')

        shortcut_id = str(ObjectId())

        # Clean tags
        add_tags = [tag.strip() for tag in add_tags if tag.strip()]
        remove_tags = [tag.strip() for tag in remove_tags if tag.strip()]
        suggested_messages = [msg.strip() for msg in suggested_messages if msg.strip()]

        # Add tags to tag collection if they don't exist
        tag_collection = get_tag_collection()
        for tag in add_tags:
            existing = tag_collection.find_one({'name': tag})
            if not existing:
                tag_collection.insert_one({
                    'tag_id': str(ObjectId()),
                    'name': tag,
                    'color': '#007bff',
                    'created_at': timezone.now()
                })

        # Prepare shortcut document
        shortcut_data = {
            'shortcut_id': shortcut_id,
            'title': title,
            'content': content,
            'created_at': timezone.now(),
            'action': {
                'add_tags': add_tags,
                'remove_tags': remove_tags
            },
            'suggested_messages': suggested_messages
        }

        get_shortcut_collection().insert_one(shortcut_data)
        return redirect('shortcut-list')

    return render(request, 'support/add_shortcut.html')



# Edit a shortcut
def edit_shortcut(request, shortcut_id):
    shortcut = get_shortcut_collection().find_one({'_id': ObjectId(shortcut_id)})
    if request.method == 'POST':
        get_shortcut_collection().update_one({'_id': ObjectId(shortcut_id)}, {
            '$set': {
                'title': request.POST.get('title'),
                'content': request.POST.get('content'),
                'updated_at': timezone.now()
            }
        })
        return redirect('shortcut-list')
    return render(request, 'support/edit_shortcut.html', {'shortcut': shortcut})

# Delete a shortcut
def delete_shortcut(request, shortcut_id):
    get_shortcut_collection().delete_one({'_id': ObjectId(shortcut_id)})
    return redirect('shortcut-list')


# List all tags
def tag_list(request):
    tags = list(get_tag_collection().find())
    for t in tags:
        t['id'] = str(t['_id'])
    return render(request, 'support/tag_list.html', {'tags': tags})

# Add a new tag
def add_tag(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        color = request.POST.get('color') or "#cccccc"
        tag_id = str(ObjectId())
        
        get_tag_collection().insert_one({
            'tag_id': tag_id,
            'name': name,
            'color': color,
            'created_at': timezone.now()
        })
        return redirect('tag-list')
    return render(request, 'support/add_tag.html')

# Edit a tag
def edit_tag(request, tag_id):
    tag = get_tag_collection().find_one({'_id': ObjectId(tag_id)})
    if request.method == 'POST':
        get_tag_collection().update_one({'_id': ObjectId(tag_id)}, {
            '$set': {
                'name': request.POST.get('name'),
                'color': request.POST.get('color') or "#cccccc",
                'updated_at': timezone.now()
            }
        })
        return redirect('tag-list')
    return render(request, 'support/edit_tag.html', {'tag': tag})

# Delete a tag
def delete_tag(request, tag_id):
    get_tag_collection().delete_one({'_id': ObjectId(tag_id)})
    return redirect('tag-list')

import json

def add_trigger(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        message = request.POST.get('message')
        # url_contains = request.POST.get('url_contains')
        # time_on_page_sec = int(request.POST.get('time_on_page_sec') or 0)
        widget_id = request.POST.get('widget_id')  # <-- Get widget ID from the form
        # tags = [t.strip() for t in request.POST.get('tags', '').split(',') if t.strip()]
        is_active = request.POST.get('is_active', 'true').lower() == 'true'
        
        # Optional suggested replies as comma-separated values
        suggested_raw = request.POST.get('suggested_replies', '[]')
        try:
            suggested_replies = json.loads(suggested_raw)
            if not isinstance(suggested_replies, list):
                raise ValueError
        except Exception:
            return render(request, 'support/add_trigger.html', {
                'error': 'Suggested replies must be a valid JSON list'
            })
            
        if not widget_id:
            return render(request, 'support/add_trigger.html', {
                'error': 'Widget ID is required'
            })

        trigger_collection = get_trigger_collection()

        # Count only triggers for this widget to determine the order
        current_count = trigger_collection.count_documents({'widget_id': widget_id})

        trigger_data = {
            'trigger_id': str(ObjectId()),
            'widget_id': widget_id,  # <-- Save widget ID
            'name': name,
            'message': message,
            # 'conditions': {
            #     'url_contains': url_contains,
            #     'time_on_page_sec': time_on_page_sec
            # },
            # 'tags': tags,
            'is_active': is_active,
            'created_at': timezone.now(),
            'order': current_count + 1
        }
        if suggested_replies:
            trigger_data['suggested_replies'] = suggested_replies

        # # Insert new tags
        # tag_collection = get_tag_collection()
        # for tag in tags:
        #     if not tag_collection.find_one({'name': tag}):
        #         tag_collection.insert_one({
        #             'tag_id': str(ObjectId()),
        #             'name': tag,
        #             'color': '#28a745',
        #             'created_at': timezone.now()
        #         })

        trigger_collection.insert_one(trigger_data)
        return redirect('/admin/')

    return render(request, 'support/add_trigger.html')



from rest_framework.decorators import api_view
from rest_framework.response import Response
from wish_bot.db import get_trigger_collection

@api_view(['PUT'])
def update_predefined_messages(request):
    widget_id = request.data.get('widget_id')
    updated_messages = request.data.get('messages', [])

    if not widget_id or not isinstance(updated_messages, list):
        return Response({'error': 'Invalid input data'}, status=400)

    collection = get_trigger_collection()

    modified_count = 0

    for i, msg in enumerate(updated_messages):
        trigger_id = msg.get('trigger_id')
        if not trigger_id:
            continue  # Skip invalid entry

        update_fields = {
            'message': msg.get('message'),
            'name': msg.get('name', ''),
            'is_active': msg.get('is_active', True),
            'order': i + 1,
            'suggested_replies': msg.get('suggested_replies', []), # <-- New field
            'updated_at': timezone.now()
        }

        result = collection.update_one(
            {'trigger_id': trigger_id, 'widget_id': widget_id},
            {'$set': update_fields}
        )
        
        modified_count += result.modified_count

    return Response({'success': True, 'modified_count': modified_count})


from django.http import JsonResponse


def get_triggers_api(request):
    """
    GET API to retrieve triggers with optional filters:
    - widget_id: str
    - is_active: true/false (case insensitive)

    Example: /get-triggers?widget_id=abc123&is_active=true
    """
    widget_id = request.GET.get('widget_id')
    is_active_param = request.GET.get('is_active')

    trigger_collection = get_trigger_collection()

    query = {}
    if widget_id:
        query['widget_id'] = widget_id

    if is_active_param is not None:
        if is_active_param.lower() == 'true':
            query['is_active'] = True
        elif is_active_param.lower() == 'false':
            query['is_active'] = False

    triggers = list(trigger_collection.find(query))

    for t in triggers:
        t['trigger_id'] = str(t.get('trigger_id', ''))
        t['_id'] = str(t['_id'])
        if 'created_at' in t and hasattr(t['created_at'], 'isoformat'):
            t['created_at'] = t['created_at'].isoformat()

    return JsonResponse({'triggers': triggers}, safe=False)


from django.shortcuts import render
def trigger_test_view(request):
    return render(request, 'support/trigger_test.html')
