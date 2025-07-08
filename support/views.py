import logging
from venv import logger
import json
from django.shortcuts import render, redirect
from django.utils import timezone
from bson import ObjectId
from authentication.utils import jwt_required, agent_or_superadmin_required
from wish_bot.db import get_ticket_collection,get_tag_collection, get_agent_collection
from wish_bot.db import get_shortcut_collection,get_trigger_collection

import random
logger = logging.getLogger(__name__)

def get_random_color():
    colors = ['#FF5733', '#33FF57', '#3357FF', '#F39C12', '#9B59B6', '#1ABC9C']
    return random.choice(colors)

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




@jwt_required
@agent_or_superadmin_required
def shortcut_list(request):
    if request.method == 'GET':
        shortcuts = list(get_shortcut_collection().find())
        for s in shortcuts:
            s['id'] = str(s['_id'])
            s.pop('_id', None)  # remove raw Mongo _id
        return JsonResponse({'shortcuts': shortcuts}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=400)



@jwt_required
@agent_or_superadmin_required
def shortcut_detail(request, shortcut_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    shortcut_collection = get_shortcut_collection()
    shortcut = shortcut_collection.find_one({'shortcut_id': shortcut_id})

    if not shortcut:
        return JsonResponse({'error': 'Shortcut not found'}, status=404)

    # Convert ObjectId fields to strings if needed
    shortcut['_id'] = str(shortcut['_id'])
    shortcut['created_at'] = str(shortcut.get('created_at'))
    shortcut['updated_at'] = str(shortcut.get('updated_at')) if shortcut.get('updated_at') else None

    return JsonResponse({'success': True, 'shortcut': shortcut})



@jwt_required
# @agent_or_superadmin_required
def add_shortcut(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)

        title = data.get('title', '').strip()
        content = data.get('content', '').strip()

        if not title or not content:
            logger.warning("Shortcut creation failed: 'title' or 'content' missing")
            return JsonResponse({
                'success': False,
                'message': "Both 'title' and 'content' are required."
            }, status=400)

        add_tags = data.get('add_tags', '').split(',')
        remove_tags = data.get('remove_tags', '').split(',')
        suggested_messages = data.get('suggested_messages', '').split('\n')

        add_tags = [tag.strip() for tag in add_tags if tag.strip()]
        remove_tags = [tag.strip() for tag in remove_tags if tag.strip()]
        suggested_messages = [msg.strip() for msg in suggested_messages if msg.strip()]

        shortcut_collection = get_shortcut_collection()

        # Check for duplicate title
        if shortcut_collection.find_one({'title': title}):
            logger.info(f"Shortcut not created: title '{title}' already exists")
            return JsonResponse({
                'success': False,
                'message': f"A shortcut with the title '{title}' already exists."
            }, status=400)

        tag_collection = get_tag_collection()
        for tag in add_tags:
            if not tag_collection.find_one({'name': tag}):
                tag_collection.insert_one({
                    'tag_id': str(ObjectId()),
                    'name': tag,
                    'color': '#007bff',
                    'created_at': timezone.now()
                })

        shortcut_id = str(ObjectId())
        admin_id = request.jwt_user.get('admin_id')

        shortcut_data = {
            'shortcut_id': shortcut_id,
            'title': title,
            'content': content,
            'admin_id': admin_id,
            'tags': add_tags,
            'created_at': timezone.now(),
            'action': {
                'add_tags': add_tags,
                'remove_tags': remove_tags
            },
            'suggested_messages': suggested_messages
        }

        shortcut_collection.insert_one(shortcut_data)

        logger.info(f"Shortcut created by admin_id={admin_id} | title='{title}' | shortcut_id={shortcut_id}")

        return JsonResponse({
            'success': True,
            'message': 'Shortcut added successfully',
            'shortcut_id': shortcut_id,
            'shortcut_data': {
                'title': title,
                'content': content,
                'admin_id': admin_id,
                'tags': add_tags,
                'created_at': timezone.now(),
                'action': {
                    'add_tags': add_tags,
                    'remove_tags': remove_tags
                },
                'suggested_messages': suggested_messages
            }
        })

    return JsonResponse({'error': 'Invalid request method'}, status=400)


@jwt_required
@agent_or_superadmin_required
def edit_shortcut(request, shortcut_id):
    if request.method != 'PATCH':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)

    shortcut_col = get_shortcut_collection()
    shortcut = shortcut_col.find_one({'shortcut_id': shortcut_id})
    if not shortcut:
        return JsonResponse({'error': 'Shortcut not found'}, status=404)

    def parse_tags(value):
        if isinstance(value, list):
            return [v.strip() for v in value if v and str(v).strip()]
        return [v.strip() for v in str(value).split(',') if v.strip()]

    update_doc = {}

    # ---- Title Check ----
    title = data.get('title')
    if title is not None:
        title = title.strip()
        if not title:
            return JsonResponse({'error': "'title' cannot be empty"}, status=400)
        if shortcut_col.find_one({'title': title, 'shortcut_id': {'$ne': shortcut_id}}):
            return JsonResponse({'error': f"Another shortcut already uses title '{title}'"}, status=400)
        update_doc['title'] = title

    # ---- Content Check ----
    content = data.get('content')
    if content is not None:
        content = content.strip()
        if not content:
            return JsonResponse({'error': "'content' cannot be empty"}, status=400)
        if shortcut_col.find_one({'content': content, 'shortcut_id': {'$ne': shortcut_id}}):
            return JsonResponse({'error': f"Another shortcut already uses this content"}, status=400)
        update_doc['content'] = content

    # ---- Tags ----
    if 'tags' in data:
        update_doc['tags'] = parse_tags(data['tags'])

    # ---- Action Tags ----
    action_update = {}
    if 'add_tags' in data:
        action_update['add_tags'] = parse_tags(data['add_tags'])
    if 'remove_tags' in data:
        action_update['remove_tags'] = parse_tags(data['remove_tags'])

    if action_update:
        current_action = shortcut.get('action', {})
        current_action.update(action_update)
        update_doc['action'] = current_action

    # ---- Suggested Messages ----
    if 'suggested_messages' in data:
        messages = data['suggested_messages']
        if isinstance(messages, list):
            clean_messages = [m.strip() for m in messages if m and str(m).strip()]
        else:
            clean_messages = [m.strip() for m in str(messages).split('\n') if m.strip()]
        update_doc['suggested_messages'] = clean_messages

    # Always set updated_at even if no other fields were updated
    update_doc['updated_at'] = timezone.now()

    if len(update_doc) == 1:  # Only 'updated_at' was set
        return JsonResponse({'success': False, 'message': 'No editable fields supplied'}, status=400)

    shortcut_col.update_one({'shortcut_id': shortcut_id}, {'$set': update_doc})

    logger.info(
        f"[Shortcut Updated] shortcut_id={shortcut_id} by admin_id={request.jwt_user.get('admin_id')} | fields_updated={list(update_doc.keys())}"
    )

    return JsonResponse({'success': True, 'message': 'Shortcut updated successfully'})


@jwt_required
@agent_or_superadmin_required
def delete_shortcut(request, shortcut_id):
    delete_result = get_shortcut_collection().delete_one({'shortcut_id': shortcut_id})

    if delete_result.deleted_count == 1:
        return JsonResponse({'success': True, 'message': 'Shortcut deleted successfully'})
    else:
        return JsonResponse({'error': 'Shortcut not found'}, status=404)





@jwt_required
@agent_or_superadmin_required
def tag_list(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    tags = list(get_tag_collection().find())
    for t in tags:
        t['id'] = str(t['_id'])
        t['_id'] = str(t['_id'])
        t['created_at'] = str(t.get('created_at'))
        if 'updated_at' in t:
            t['updated_at'] = str(t['updated_at'])
    return JsonResponse({'success': True, 'tags': tags})



@jwt_required
@agent_or_superadmin_required
def tag_detail(request, tag_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        tag = get_tag_collection().find_one({'tag_id': tag_id})
    except Exception:
        return JsonResponse({'error': 'Invalid tag ID format'}, status=400)

    if not tag:
        return JsonResponse({'error': 'Tag not found'}, status=404)

    tag['_id'] = str(tag['_id'])
    tag['created_at'] = str(tag.get('created_at'))
    if 'updated_at' in tag:
        tag['updated_at'] = str(tag['updated_at'])

    return JsonResponse({'success': True, 'tag': tag})




@jwt_required
@agent_or_superadmin_required
def add_tag(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method. Use POST.'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)

    name = data.get('name', '').strip()
    color = data.get('color', '#cccccc').strip()

    if not name:
        return JsonResponse({'error': "'name' is required"}, status=400)

    tag_collection = get_tag_collection()

    # Optional: prevent duplicate tag names
    if tag_collection.find_one({'name': name}):
        return JsonResponse({'error': f"Tag with name '{name}' already exists"}, status=409)

    tag_id = str(ObjectId())
    tag = {
        'tag_id': tag_id,
        'name': name,
        'color': color,
        'created_at': timezone.now()
    }

    tag_collection.insert_one(tag)

    return JsonResponse({
        'success': True,
        'message': 'Tag added successfully',
        'tag_id': tag_id,
        'tag': {
            'name': name,
            'color': color,
            'created_at': str(tag['created_at'])
        }
    }, status=201)



@jwt_required
@agent_or_superadmin_required
def edit_tag(request, tag_id):
    if request.method != 'PATCH':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)

    name = data.get('name', '').strip()
    color = data.get('color', '#cccccc').strip()

    if not name:
        return JsonResponse({'error': "'name' is required"}, status=400)

    tag_collection = get_tag_collection()

    # ✅ Prevent duplicate tag name (excluding current tag_id)
    if tag_collection.find_one({'name': name, 'tag_id': {'$ne': tag_id}}):
        return JsonResponse({'error': f"Tag with name '{name}' already exists"}, status=409)

    # ✅ Perform update
    updated_at = timezone.now()
    result = tag_collection.update_one(
        {'tag_id': tag_id},
        {
            '$set': {
                'name': name,
                'color': color,
                'updated_at': updated_at
            }
        }
    )

    if result.modified_count == 0:
        return JsonResponse({'error': 'Tag not found or not modified'}, status=404)

    # ✅ Return updated tag
    updated_tag = tag_collection.find_one({'tag_id': tag_id})
    updated_tag['_id'] = str(updated_tag['_id'])
    updated_tag['created_at'] = str(updated_tag.get('created_at', ''))
    updated_tag['updated_at'] = str(updated_tag.get('updated_at', ''))

    return JsonResponse({
        'success': True,
        'message': 'Tag updated successfully',
        'tag': updated_tag
    }, status=200)



@jwt_required
@agent_or_superadmin_required
def delete_tag(request, tag_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    result = get_tag_collection().delete_one({'tag_id': tag_id})
    if result.deleted_count == 0:
        return JsonResponse({'error': 'Tag not found'}, status=404)

    return JsonResponse({'success': True, 'message': 'Tag deleted successfully'})




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
