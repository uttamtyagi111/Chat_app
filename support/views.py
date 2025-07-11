import logging
from turtle import up
from venv import logger
import json
from django.shortcuts import render, redirect
from django.utils import timezone
from bson import ObjectId
from urllib3 import request
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
@agent_or_superadmin_required
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

        # Get tags from user input - can be array or single string
        tags_input = data.get('tags', [])
        if isinstance(tags_input, str):
            # If it's a string, split by comma or newline
            tags = [tag.strip() for tag in tags_input.replace('\n', ',').split(',') if tag.strip()]
        elif isinstance(tags_input, list):
            # If it's already a list, just clean it up
            tags = [tag.strip() for tag in tags_input if tag.strip()]
        else:
            tags = []

        suggested_messages = data.get('suggested_messages', '')
        if isinstance(suggested_messages, str):
            suggested_messages = suggested_messages.split('\n')
        elif not isinstance(suggested_messages, list):
            suggested_messages = []
        
        suggested_messages = [msg.strip() for msg in suggested_messages if msg.strip()]

        shortcut_collection = get_shortcut_collection()

        # Check for duplicate title
        if shortcut_collection.find_one({'title': title}):
            logger.info(f"Shortcut not created: title '{title}' already exists")
            return JsonResponse({
                'success': False,
                'message': f"A shortcut with the title '{title}' already exists."
            }, status=400)

        # Create tags if they don't exist
        tag_collection = get_tag_collection()
        for tag in tags:
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
            'tags': tags,
            'created_at': timezone.now(),
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
                'tags': tags,
                'created_at': timezone.now(),
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

# def add_trigger(request):
#     if request.method == 'POST':
#         name = request.POST.get('name')
#         message = request.POST.get('message')
#         # url_contains = request.POST.get('url_contains')
#         # time_on_page_sec = int(request.POST.get('time_on_page_sec') or 0)
#         widget_id = request.POST.get('widget_id')  # <-- Get widget ID from the form
#         # tags = [t.strip() for t in request.POST.get('tags', '').split(',') if t.strip()]
#         is_active = request.POST.get('is_active', 'true').lower() == 'true'
        
#         # Optional suggested replies as comma-separated values
#         suggested_raw = request.POST.get('suggested_replies', '[]')
#         try:
#             suggested_replies = json.loads(suggested_raw)
#             if not isinstance(suggested_replies, list):
#                 raise ValueError
#         except Exception:
#             return render(request, 'support/add_trigger.html', {
#                 'error': 'Suggested replies must be a valid JSON list'
#             })
            
#         if not widget_id:
#             return render(request, 'support/add_trigger.html', {
#                 'error': 'Widget ID is required'
#             })

#         trigger_collection = get_trigger_collection()

#         # Count only triggers for this widget to determine the order
#         current_count = trigger_collection.count_documents({'widget_id': widget_id})

#         trigger_data = {
#             'trigger_id': str(ObjectId()),
#             'widget_id': widget_id,  # <-- Save widget ID
#             'name': name,
#             'message': message,
#             # 'conditions': {
#             #     'url_contains': url_contains,
#             #     'time_on_page_sec': time_on_page_sec
#             # },
#             # 'tags': tags,
#             'is_active': is_active,
#             'created_at': timezone.now(),
#             'order': current_count + 1
#         }
#         if suggested_replies:
#             trigger_data['suggested_replies'] = suggested_replies

#         # # Insert new tags
#         # tag_collection = get_tag_collection()
#         # for tag in tags:
#         #     if not tag_collection.find_one({'name': tag}):
#         #         tag_collection.insert_one({
#         #             'tag_id': str(ObjectId()),
#         #             'name': tag,
#         #             'color': '#28a745',
#         #             'created_at': timezone.now()
#         #         })

#         trigger_collection.insert_one(trigger_data)
#         return redirect('/admin/')

#     return render(request, 'support/add_trigger.html')

# from django.http import JsonResponse
# import json
# from bson import ObjectId
# from django.utils import timezone

# def add_trigger(request):
#     if request.method == 'POST':
#         try:
#             name = request.POST.get('name')
#             message = request.POST.get('message')
#             widget_id = request.POST.get('widget_id')
#             is_active = request.POST.get('is_active', 'true').lower() == 'true'
            
#             # Validate required fields
#             if not name:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'Name is required'
#                 }, status=400)
            
#             if not message:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'Message is required'
#                 }, status=400)
            
#             if not widget_id:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'Widget ID is required'
#                 }, status=400)
            
#             # Parse suggested replies
#             suggested_raw = request.POST.get('suggested_replies', '[]')
#             try:
#                 suggested_replies = json.loads(suggested_raw)
#                 if not isinstance(suggested_replies, list):
#                     raise ValueError
#             except Exception:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'Suggested replies must be a valid JSON list'
#                 }, status=400)
            
#             trigger_collection = get_trigger_collection()
            
#             # Count only triggers for this widget to determine the order
#             current_count = trigger_collection.count_documents({'widget_id': widget_id})
            
#             trigger_data = {
#                 'trigger_id': str(ObjectId()),
#                 'widget_id': widget_id,
#                 'name': name,
#                 'message': message,
#                 'is_active': is_active,
#                 'created_at': timezone.now(),
#                 'order': current_count + 1
#             }
            
#             if suggested_replies:
#                 trigger_data['suggested_replies'] = suggested_replies
            
#             # Insert the trigger
#             result = trigger_collection.insert_one(trigger_data)
            
#             if result.inserted_id:
#                 return JsonResponse({
#                     'success': True,
#                     'message': 'Trigger added successfully',
#                     'data': {
#                         'trigger_id': trigger_data['trigger_id'],
#                         'name': name,
#                         'message': message,
#                         'widget_id': widget_id,
#                         'order': trigger_data['order'],
#                         'is_active': is_active
#                     }
#                 })
#             else:
#                 return JsonResponse({
#                     'success': False,
#                     'error': 'Failed to insert trigger'
#                 }, status=500)
                
#         except Exception as e:
#             return JsonResponse({
#                 'success': False,
#                 'error': f'An error occurred: {str(e)}'
#             }, status=500)
    
#     # GET request
#     return JsonResponse({
#         'success': False,
#         'error': 'Only POST method is allowed'
#     }, status=405)

# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from wish_bot.db import get_trigger_collection

# @api_view(['PUT'])
# def update_predefined_messages(request):
#     widget_id = request.data.get('widget_id')
#     updated_messages = request.data.get('messages', [])

#     if not widget_id or not isinstance(updated_messages, list):
#         return Response({'error': 'Invalid input data'}, status=400)

#     collection = get_trigger_collection()

#     modified_count = 0

#     for i, msg in enumerate(updated_messages):
#         trigger_id = msg.get('trigger_id')
#         if not trigger_id:
#             continue  # Skip invalid entry

#         update_fields = {
#             'message': msg.get('message'),
#             'name': msg.get('name', ''),
#             'is_active': msg.get('is_active', True),
#             'order': i + 1,
#             'suggested_replies': msg.get('suggested_replies', []), # <-- New field
#             'updated_at': timezone.now()
#         }

#         result = collection.update_one(
#             {'trigger_id': trigger_id, 'widget_id': widget_id},
#             {'$set': update_fields}
#         )
        
#         modified_count += result.modified_count

#     return Response({'success': True, 'modified_count': modified_count})


# from django.http import JsonResponse


# def get_triggers_api(request):
#     """
#     GET API to retrieve triggers with optional filters:
#     - widget_id: str
#     - is_active: true/false (case insensitive)

#     Example: /get-triggers?widget_id=abc123&is_active=true
#     """
#     widget_id = request.GET.get('widget_id')
#     is_active_param = request.GET.get('is_active')

#     trigger_collection = get_trigger_collection()

#     query = {}
#     if widget_id:
#         query['widget_id'] = widget_id

#     if is_active_param is not None:
#         if is_active_param.lower() == 'true':
#             query['is_active'] = True
#         elif is_active_param.lower() == 'false':
#             query['is_active'] = False

#     triggers = list(trigger_collection.find(query))

#     for t in triggers:
#         t['trigger_id'] = str(t.get('trigger_id', ''))
#         t['_id'] = str(t['_id'])
#         if 'created_at' in t and hasattr(t['created_at'], 'isoformat'):
#             t['created_at'] = t['created_at'].isoformat()

#     return JsonResponse({'triggers': triggers}, safe=False)
from django.http import JsonResponse
import json
from bson import ObjectId
from django.utils import timezone
from wish_bot.db import get_trigger_collection
from authentication.utils import jwt_required,is_agent_assigned_to_widget


@jwt_required
def add_trigger(request):
    if request.method == 'POST':
        try:
            user = request.jwt_user
            widget_id = request.POST.get('widget_id')

            if not is_agent_assigned_to_widget(request, widget_id):
                return JsonResponse({'success': False, 'error': 'Unauthorized: Not assigned to this widget'}, status=403)

            name = request.POST.get('name')
            message = request.POST.get('message')
            is_active = request.POST.get('is_active', 'true').lower() == 'true'

            if not name or not message or not widget_id:
                return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)

            # Check for existing trigger with the same name for the same widget
            trigger_collection = get_trigger_collection()
            existing_trigger = trigger_collection.find_one({'widget_id': widget_id, 'name': name})
            if existing_trigger:
                return JsonResponse({
                    'success': False,
                    'error': f"A trigger with the name '{name}' already exists for this widget"
                }, status=400)

            suggested_raw = request.POST.get('suggested_replies', '[]')
            try:
                suggested_replies = json.loads(suggested_raw)
                if not isinstance(suggested_replies, list):
                    raise ValueError
            except Exception:
                return JsonResponse({'success': False, 'error': 'Suggested replies must be a valid JSON list'}, status=400)

            current_count = trigger_collection.count_documents({'widget_id': widget_id})

            trigger_data = {
                'trigger_id': str(ObjectId()),
                'widget_id': widget_id,
                'name': name,
                'message': message,
                'is_active': is_active,
                'created_at': timezone.now(),
                'order': current_count + 1
            }

            if suggested_replies:
                trigger_data['suggested_replies'] = suggested_replies

            result = trigger_collection.insert_one(trigger_data)

            if result.inserted_id:
                return JsonResponse({
                    'success': True,
                    'message': 'Trigger added successfully',
                    'data': {
                        'trigger_id': trigger_data['trigger_id'],
                        'name': name,
                        'message': message,
                        'widget_id': widget_id,
                        'order': trigger_data['order'],
                        'is_active': is_active
                    }
                })

            return JsonResponse({'success': False, 'error': 'Failed to insert trigger'}, status=500)

        except Exception as e:
            return JsonResponse({'success': False, 'error': f'An error occurred: {str(e)}'}, status=500)

    return JsonResponse({'success': False, 'error': 'Only POST method is allowed'}, status=405)

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone
from bson import ObjectId
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from authentication.jwt_auth import JWTAuthentication
from wish_bot.db import get_trigger_collection
from rest_framework.response import Response
from rest_framework import status
from wish_bot.db import get_trigger_collection
from authentication.jwt_auth import JWTAuthentication
from django.utils import timezone


class PatchTriggerAPIView(APIView):
    authentication_classes = [JWTAuthentication]

    def patch(self, request, trigger_id):
        widget_id = request.data.get('widget_id')
        if not widget_id:
            return Response({'error': 'widget_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = request.user
            role = request.user.get('role')
            assigned_widgets = request.user.get('assigned_widgets', [])

            if role == 'agent' and widget_id not in assigned_widgets:
                return Response({'error': 'Unauthorized: Not assigned to this widget'}, status=403)
# This is your SimpleUser object set by JWTAuthentication


            # Inline role-based access check
            if role == 'agent' and widget_id not in assigned_widgets:
                return Response({'error': 'Unauthorized: Not assigned to this widget'}, status=status.HTTP_403_FORBIDDEN)

            # If superadmin or agent with access -> continue
            collection = get_trigger_collection()
            update_fields = {}

            if 'name' in request.data:
                new_name = request.data['name']
                existing = collection.find_one({
                    'widget_id': widget_id,
                    'name': new_name,
                    'trigger_id': {'$ne': trigger_id}
                })
                if existing:
                    return Response({'error': f"A trigger with the name '{new_name}' already exists"}, status=400)
                update_fields['name'] = new_name

            if 'message' in request.data:
                update_fields['message'] = request.data['message']

            if 'is_active' in request.data:
                update_fields['is_active'] = request.data['is_active']

            if 'suggested_replies' in request.data:
                replies = request.data['suggested_replies']
                if not isinstance(replies, list):
                    return Response({'error': 'suggested_replies must be a list'}, status=400)
                update_fields['suggested_replies'] = replies

            if 'order' in request.data:
                order = request.data['order']
                if not isinstance(order, int) or order <= 0:
                    return Response({'error': 'order must be a positive integer'}, status=400)
                update_fields['order'] = order

            if not update_fields:
                return Response({'error': 'No valid fields provided to update'}, status=400)

            update_fields['updated_at'] = timezone.now()

            result = collection.update_one(
                {'trigger_id': trigger_id, 'widget_id': widget_id},
                {'$set': update_fields}
            )
            
              # ✅ Return the updated trigger document
            updated_trigger = collection.find_one({'trigger_id': trigger_id, 'widget_id': widget_id})
            if updated_trigger:
                updated_trigger['_id'] = str(updated_trigger['_id'])  # Convert ObjectId to str
                updated_trigger['updated_at'] = updated_trigger.get('updated_at').isoformat()


            if result.matched_count == 0:
                return Response({'error': 'Trigger not found or widget_id mismatch'}, status=404)

            return Response({
                'success': True,
                'message': 'Trigger updated successfully',
                'updated_fields': updated_trigger
            })

        except Exception as e:
            return Response({'error': f'Unexpected error: {str(e)}'}, status=500)

from rest_framework.decorators import api_view
from rest_framework.response import Response

# from authentication.decorators import jwt_required
# from .utils import is_agent_assigned_to_widget  # or define inline

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone
from wish_bot.db import get_trigger_collection
from authentication.utils import jwt_required
from authentication.utils import is_agent_assigned_to_widget

@api_view(['PATCH'])
@jwt_required
def update_trigger_message(request, trigger_id):
    # user = request.jwt_user
    widget_id = request.data.get('widget_id')
    
    if not widget_id:
        return Response({'error': 'widget_id is required'}, status=400)

    # ✅ Role-based widget access: agent must be assigned, superadmin allowed
    if not is_agent_assigned_to_widget(request, widget_id):
        return Response({'error': 'Unauthorized: Not assigned to this widget'}, status=403)

    collection = get_trigger_collection()
    update_fields = {}

    # Optional fields
    if 'message' in request.data:
        update_fields['message'] = request.data['message']

    if 'name' in request.data:
        update_fields['name'] = request.data['name']

    if 'is_active' in request.data:
        if not isinstance(request.data['is_active'], bool):
            return Response({'error': 'is_active must be a boolean'}, status=400)
        update_fields['is_active'] = request.data['is_active']

    if 'suggested_replies' in request.data:
        replies = request.data['suggested_replies']
        if not isinstance(replies, list):
            return Response({'error': 'suggested_replies must be a list'}, status=400)
        update_fields['suggested_replies'] = replies

    if 'order' in request.data:
        order = request.data['order']
        if not isinstance(order, int) or order <= 0:
            return Response({'error': 'order must be a positive integer'}, status=400)
        update_fields['order'] = order

    if not update_fields:
        return Response({'error': 'No valid fields provided to update'}, status=400)

    update_fields['updated_at'] = timezone.now()

    result = collection.update_one(
        {'trigger_id': trigger_id, 'widget_id': widget_id},
        {'$set': update_fields}
    )

    if result.matched_count == 0:
        return Response({'error': 'Trigger not found or widget_id mismatch'}, status=404)

    return Response({
        'success': True,
        'message': 'Trigger updated successfully',
        'updated_fields': list(update_fields.keys())
    })



from wish_bot.db import get_widget_collection
@jwt_required
def get_triggers_api(request):
    user = request.jwt_user
    role = user.get("role")
    assigned_widgets = user.get("assigned_widgets", [])

    widget_id = request.GET.get('widget_id')
    is_active_param = request.GET.get('is_active')

    # Validate agent access
    if role == 'agent':
        if not widget_id:
            return JsonResponse({'error': 'widget_id is required for agents'}, status=400)

        if widget_id not in assigned_widgets:
            return JsonResponse({'error': 'Unauthorized: Not assigned to this widget'}, status=403)

        # Verify widget is active
        widget_collection = get_widget_collection()
        widget = widget_collection.find_one({'widget_id': widget_id, 'is_active': True})
        if not widget:
            return JsonResponse({'error': 'Widget is either not found or not active'}, status=403)

    elif role != 'superadmin':
        return JsonResponse({'error': 'Access denied: Invalid role'}, status=403)

    # Build query
    query = {}
    if widget_id:
        query['widget_id'] = widget_id

    if is_active_param:
        if is_active_param.lower() == 'true':
            query['is_active'] = True
        elif is_active_param.lower() == 'false':
            query['is_active'] = False

    # Fetch and format triggers
    trigger_collection = get_trigger_collection()
    triggers = list(trigger_collection.find(query))

    for t in triggers:
        t['trigger_id'] = str(t.get('trigger_id', ''))
        t['_id'] = str(t['_id'])
        if 'created_at' in t and hasattr(t['created_at'], 'isoformat'):
            t['created_at'] = t['created_at'].isoformat()

    return JsonResponse({'triggers': triggers}, safe=False)


@jwt_required
def get_trigger_detail(request, trigger_id):
    user = request.jwt_user
    role = user.get("role")
    assigned_widgets = user.get("assigned_widgets", [])

    trigger_collection = get_trigger_collection()
    widget_collection = get_widget_collection()

    # Find trigger
    trigger = trigger_collection.find_one({'trigger_id': trigger_id})
    if not trigger:
        return JsonResponse({'error': 'Trigger not found'}, status=404)

    widget_id = trigger.get('widget_id')

    # Role-based check
    if role == 'agent':
        if widget_id not in assigned_widgets:
            return JsonResponse({'error': 'Unauthorized: Not assigned to this widget'}, status=403)

        widget = widget_collection.find_one({'widget_id': widget_id, 'is_active': True})
        if not widget:
            return JsonResponse({'error': 'Widget is either not found or not active'}, status=403)

    elif role != 'superadmin':
        return JsonResponse({'error': 'Access denied: Invalid role'}, status=403)

    # Format trigger
    trigger['trigger_id'] = str(trigger.get('trigger_id', ''))
    trigger['_id'] = str(trigger.get('_id', ''))

    if 'created_at' in trigger and hasattr(trigger['created_at'], 'isoformat'):
        trigger['created_at'] = trigger['created_at'].isoformat()

    return JsonResponse({'trigger': trigger}, safe=False)

from django.shortcuts import render
def trigger_test_view(request):
    return render(request, 'support/trigger_test.html')
