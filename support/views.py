import logging
from django.http import JsonResponse
import json
from django.shortcuts import render, redirect
from django.utils import timezone
from bson import ObjectId
from authentication.utils import jwt_required, agent_or_superadmin_required
from wish_bot.db import get_admin_collection, get_ticket_collection,get_tag_collection, get_agent_collection
from wish_bot.db import get_shortcut_collection,get_trigger_collection,get_room_collection
from rest_framework.decorators import api_view
from rest_framework.response import Response
from authentication.utils import is_agent_assigned_to_widget
import random
from rest_framework.views import APIView
from rest_framework import status
from authentication.jwt_auth import JWTAuthentication 

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
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    user = request.jwt_user
    role = user.get('role')
    admin_id = user.get('admin_id')

    shortcut_collection = get_shortcut_collection()

    if role == 'agent':
        admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
        if not admin_doc:
            return JsonResponse({'error': 'Agent not found'}, status=404)
        assigned_widgets = admin_doc.get('assigned_widgets', [])
        if isinstance(assigned_widgets, str):
            assigned_widgets = [assigned_widgets]
        shortcuts = list(shortcut_collection.find({'widget_id': {'$in': assigned_widgets}}))
    else:
        shortcuts = list(shortcut_collection.find())

    for s in shortcuts:
        s['id'] = str(s['_id'])
        s.pop('_id', None)
        s['created_at'] = str(s.get('created_at', ''))
        s['updated_at'] = str(s.get('updated_at', '')) if s.get('updated_at') else None

    return JsonResponse({'shortcuts': shortcuts}, status=200)




@jwt_required
@agent_or_superadmin_required
def shortcut_detail(request, shortcut_id):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    shortcut_collection = get_shortcut_collection()
    shortcut = shortcut_collection.find_one({'shortcut_id': shortcut_id})

    if not shortcut:
        return JsonResponse({'error': 'Shortcut not found'}, status=404)

    user = request.jwt_user
    role = user.get('role')
    admin_id = user.get('admin_id')
    widget_id = shortcut.get('widget_id')

    if role == 'agent':
        admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
        if not admin_doc:
            return JsonResponse({'error': 'Agent not found'}, status=404)
        assigned_widgets = admin_doc.get('assigned_widgets', [])
        if isinstance(assigned_widgets, str):
            assigned_widgets = [assigned_widgets]
        if widget_id not in assigned_widgets:
            return JsonResponse({'error': 'Unauthorized to view this shortcut'}, status=403)

    shortcut['_id'] = str(shortcut['_id'])
    shortcut['created_at'] = str(shortcut.get('created_at'))
    shortcut['updated_at'] = str(shortcut.get('updated_at')) if shortcut.get('updated_at') else None

    return JsonResponse({'success': True, 'shortcut': shortcut})

@jwt_required
@agent_or_superadmin_required
def add_shortcut(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))

        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        widget_id = data.get('widget_id', '').strip()

        if not title or not content or not widget_id:
            return JsonResponse({'error': "'title', 'content', and 'widget_id' are required"}, status=400)

        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        if role == 'agent':
            admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = admin_doc.get('assigned_widgets', [])
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]
            if widget_id not in assigned_widgets:
                return JsonResponse({'error': 'Unauthorized to add shortcut for this widget'}, status=403)

        # ✅ Parse tags with color support
        tags_input = data.get('tags', [])
        tag_objs = []
        if isinstance(tags_input, list):
            for tag in tags_input:
                if isinstance(tag, dict):
                    tag_name = tag.get('name', '').strip()
                    tag_color = tag.get('color', '#007bff').strip()
                else:
                    tag_name = str(tag).strip()
                    tag_color = '#007bff'
                if tag_name:
                    tag_objs.append({'name': tag_name, 'color': tag_color})
        elif isinstance(tags_input, str):
            tag_objs = [{'name': t.strip(), 'color': '#007bff'} for t in tags_input.split(',') if t.strip()]

        suggested_input = data.get('suggested_messages', [])
        suggested_messages = [m.strip() for m in suggested_input.split('\n')] if isinstance(suggested_input, str) else [m.strip() for m in suggested_input if m.strip()]

        shortcut_collection = get_shortcut_collection()
        tag_collection = get_tag_collection()

        if shortcut_collection.find_one({'title': title, 'widget_id': widget_id}):
            return JsonResponse({'error': f"Shortcut with title '{title}' already exists for this widget"}, status=409)

        shortcut_id = str(ObjectId())
        shortcut_data = {
            'shortcut_id': shortcut_id,
            'title': title,
            'content': content,
            'admin_id': admin_id,
            'widget_id': widget_id,
            'tags': [t['name'] for t in tag_objs],
            'suggested_messages': suggested_messages,
            'created_at': timezone.now()
        }

        # ✅ Add/update tags
        for tag in tag_objs:
            existing_tag = tag_collection.find_one({'name': tag['name'], 'widget_id': widget_id})
            if existing_tag:
                tag_shortcuts = existing_tag.get('shortcut_id', [])
                if isinstance(tag_shortcuts, str):
                    tag_shortcuts = [tag_shortcuts]
                if shortcut_id not in tag_shortcuts:
                    tag_shortcuts.append(shortcut_id)
                tag_collection.update_one({'_id': existing_tag['_id']}, {
                    '$set': {'shortcut_id': tag_shortcuts, 'updated_at': timezone.now()}
                })
            else:
                tag_collection.insert_one({
                    'tag_id': str(ObjectId()),
                    'name': tag['name'],
                    'color': tag['color'],
                    'widget_id': widget_id,
                    'shortcut_id': [shortcut_id],
                    'created_at': timezone.now()
                })

        shortcut_collection.insert_one(shortcut_data)

        return JsonResponse({
            'success': True,
            'message': 'Shortcut added successfully',
            'shortcut_id': shortcut_id,
            'shortcut_data': {
                'title': title,
                'content': content,
                'admin_id': admin_id,
                'widget_id': widget_id,
                'tags': [t['name'] for t in tag_objs],
                'suggested_messages': suggested_messages,
                'created_at': str(shortcut_data['created_at'])
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Unexpected server error: {str(e)}'}, status=500)


@jwt_required
@agent_or_superadmin_required
def edit_shortcut(request, shortcut_id):
    if request.method != 'PATCH':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))

        shortcut_col = get_shortcut_collection()
        tag_collection = get_tag_collection()

        shortcut = shortcut_col.find_one({'shortcut_id': shortcut_id})
        if not shortcut:
            return JsonResponse({'error': 'Shortcut not found'}, status=404)

        widget_id = shortcut.get('widget_id')

        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        if role == 'agent':
            admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
            assigned_widgets = admin_doc.get('assigned_widgets', [])
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]
            if widget_id not in assigned_widgets:
                return JsonResponse({'error': 'Unauthorized to edit shortcut for this widget'}, status=403)

        update_doc = {}

        title = data.get('title')
        if title:
            title = title.strip()
            if not title:
                return JsonResponse({'error': "'title' cannot be empty"}, status=400)
            if shortcut_col.find_one({'title': title, 'widget_id': widget_id, 'shortcut_id': {'$ne': shortcut_id}}):
                return JsonResponse({'error': f"Shortcut with title '{title}' already exists for this widget"}, status=409)
            update_doc['title'] = title

        content = data.get('content')
        if content:
            content = content.strip()
            if not content:
                return JsonResponse({'error': "'content' cannot be empty"}, status=400)
            update_doc['content'] = content

        tags_input = data.get('tags')
        if tags_input is not None:
            tag_objs = []
            if isinstance(tags_input, list):
                for tag in tags_input:
                    if isinstance(tag, dict):
                        tag_name = tag.get('name', '').strip()
                        tag_color = tag.get('color', '#007bff').strip()
                    else:
                        tag_name = str(tag).strip()
                        tag_color = '#007bff'
                    if tag_name:
                        tag_objs.append({'name': tag_name, 'color': tag_color})
            elif isinstance(tags_input, str):
                tag_objs = [{'name': t.strip(), 'color': '#007bff'} for t in tags_input.split(',') if t.strip()]

            new_tag_names = [t['name'] for t in tag_objs]
            update_doc['tags'] = new_tag_names

            # ✅ Sync tags: remove from old tags
            old_tags = shortcut.get('tags', [])
            for old_tag in old_tags:
                existing_tag = tag_collection.find_one({'name': old_tag, 'widget_id': widget_id})
                if existing_tag:
                    old_list = existing_tag.get('shortcut_id', [])
                    if isinstance(old_list, str):
                        old_list = [old_list]
                    new_list = [sid for sid in old_list if sid != shortcut_id]
                    tag_collection.update_one({'_id': existing_tag['_id']}, {'$set': {'shortcut_id': new_list}})

            # ✅ Add to new tags
            for tag in tag_objs:
                existing_tag = tag_collection.find_one({'name': tag['name'], 'widget_id': widget_id})
                if existing_tag:
                    tag_shortcuts = existing_tag.get('shortcut_id', [])
                    if isinstance(tag_shortcuts, str):
                        tag_shortcuts = [tag_shortcuts]
                    if shortcut_id not in tag_shortcuts:
                        tag_shortcuts.append(shortcut_id)
                    tag_collection.update_one({'_id': existing_tag['_id']}, {
                        '$set': {'shortcut_id': tag_shortcuts, 'updated_at': timezone.now()}
                    })
                else:
                    tag_collection.insert_one({
                        'tag_id': str(ObjectId()),
                        'name': tag['name'],
                        'color': tag['color'],
                        'widget_id': widget_id,
                        'shortcut_id': [shortcut_id],
                        'created_at': timezone.now()
                    })

        if 'suggested_messages' in data:
            messages = data['suggested_messages']
            if isinstance(messages, list):
                messages = [m.strip() for m in messages if m.strip()]
            elif isinstance(messages, str):
                messages = [m.strip() for m in messages.split('\n') if m.strip()]
            update_doc['suggested_messages'] = messages

        if not update_doc:
            return JsonResponse({'error': 'No editable fields provided'}, status=400)

        update_doc['updated_at'] = timezone.now()
        shortcut_col.update_one({'shortcut_id': shortcut_id}, {'$set': update_doc})

        # 🔄 Fetch and format full updated document
        updated_shortcut = shortcut_col.find_one({'shortcut_id': shortcut_id})
        if updated_shortcut:
            updated_shortcut['_id'] = str(updated_shortcut['_id'])
            updated_shortcut['created_at'] = str(updated_shortcut.get('created_at', ''))
            updated_shortcut['updated_at'] = str(updated_shortcut.get('updated_at', ''))

        return JsonResponse({
            'success': True,
            'message': 'Shortcut updated successfully',
            'shortcut': updated_shortcut
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Unexpected server error: {str(e)}'}, status=500)
    
    
@jwt_required
@agent_or_superadmin_required
def delete_shortcut(request, shortcut_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    shortcut_collection = get_shortcut_collection()
    tag_collection = get_tag_collection()

    shortcut = shortcut_collection.find_one({'shortcut_id': shortcut_id})
    if not shortcut:
        return JsonResponse({'error': 'Shortcut not found'}, status=404)

    widget_id = shortcut.get('widget_id')

    # ✅ Role-based access for agents
    user = request.jwt_user
    role = user.get('role')
    admin_id = user.get('admin_id')
    if role == 'agent':
        admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
        assigned_widgets = admin_doc.get('assigned_widgets', [])
        if isinstance(assigned_widgets, str):
            assigned_widgets = [assigned_widgets]
        if widget_id not in assigned_widgets:
            return JsonResponse({'error': 'Unauthorized to delete shortcut from this widget'}, status=403)

    # ✅ Remove shortcut_id from all tag references
    tag_collection.update_many(
        {'shortcut_id': shortcut_id},
        {'$pull': {'shortcut_id': shortcut_id}}
    )

    # ✅ Delete the shortcut
    delete_result = shortcut_collection.delete_one({'shortcut_id': shortcut_id})

    if delete_result.deleted_count == 1:
        return JsonResponse({'success': True, 'message': 'Shortcut deleted and references cleaned'})
    else:
        return JsonResponse({'error': 'Failed to delete shortcut'}, status=500)





@jwt_required
@agent_or_superadmin_required
def tag_list(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    user = request.jwt_user
    role = user.get('role')
    admin_id = user.get('admin_id')

    tag_collection = get_tag_collection()

    # 🔐 If agent, only return tags from assigned widgets
    query = {}
    if role == 'agent':
        admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
        if not admin_doc:
            return JsonResponse({'error': 'Agent not found'}, status=404)

        assigned_widgets = admin_doc.get('assigned_widgets', [])
        if isinstance(assigned_widgets, str):
            assigned_widgets = [assigned_widgets]

        query['widget_id'] = {'$in': assigned_widgets}

    tags = list(tag_collection.find(query))
    for t in tags:
        t['id'] = str(t['_id'])
        t['_id'] = str(t['_id'])
        t['created_at'] = str(t.get('created_at'))
        if 'updated_at' in t:
            t['updated_at'] = str(t['updated_at'])

    return JsonResponse({'success': True, 'tags': tags}, status=200)



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

    user = request.jwt_user
    role = user.get('role')
    admin_id = user.get('admin_id')

    # 🔐 If agent, ensure tag belongs to assigned widgets
    if role == 'agent':
        admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
        if not admin_doc:
            return JsonResponse({'error': 'Agent not found'}, status=404)

        assigned_widgets = admin_doc.get('assigned_widgets', [])
        if isinstance(assigned_widgets, str):
            assigned_widgets = [assigned_widgets]

        if tag.get('widget_id') not in assigned_widgets:
            return JsonResponse({'error': 'You are not authorized to view this tag'}, status=403)

    tag['_id'] = str(tag['_id'])
    tag['created_at'] = str(tag.get('created_at'))
    if 'updated_at' in tag:
        tag['updated_at'] = str(tag['updated_at'])

    return JsonResponse({'success': True, 'tag': tag}, status=200)

@jwt_required
@agent_or_superadmin_required
def add_tag(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method. Use POST.'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))

        name = data.get('name')
        color = data.get('color')
        widget_id = data.get('widget_id')
        shortcut_id = data.get('shortcut_id') or []  # now array
        room_id = data.get('room_id') or []          # now array

        if not name or not widget_id:
            return JsonResponse({'error': "'name' and 'widget_id' are required"}, status=400)

        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        # ✅ Role-based access check for agent
        if role == 'agent':
            admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
            if not admin_doc:
                return JsonResponse({'error': 'Agent not found'}, status=404)

            assigned_widgets = admin_doc.get('assigned_widgets', [])
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]
            if widget_id not in assigned_widgets:
                return JsonResponse({'error': 'Unauthorized to add tags to this widget'}, status=403)

        # ✅ Validate shortcut_id (if provided)
        if isinstance(shortcut_id, str):
            shortcut_id = [shortcut_id]

        for sid in shortcut_id:
            shortcut = get_shortcut_collection().find_one({'shortcut_id': sid})
            if not shortcut or shortcut.get('widget_id') != widget_id:
                return JsonResponse({'error': f'Invalid shortcut_id: {sid} or widget mismatch'}, status=403)

        # ✅ Validate room_id (if provided)
        if isinstance(room_id, str):
            room_id = [room_id]

        for rid in room_id:
            room = get_room_collection().find_one({'room_id': rid})
            if not room or room.get('widget_id') != widget_id:
                return JsonResponse({'error': f'Invalid room_id: {rid} or widget mismatch'}, status=403)

        # ✅ Uniqueness check
        tag_collection = get_tag_collection()
        if tag_collection.find_one({'name': name, 'widget_id': widget_id}):
            return JsonResponse({'error': f"Tag '{name}' already exists for this widget"}, status=409)

        tag_id = str(ObjectId())
        created_at = timezone.now()

        tag = {
            'tag_id': tag_id,
            'name': name,
            'color': color,
            'widget_id': widget_id,
            'shortcut_id': shortcut_id,
            'room_id': room_id,
            'created_at': created_at
        }

        tag_collection.insert_one(tag)

        return JsonResponse({
            'success': True,
            'message': 'Tag added successfully',
            'tag': {
                'tag_id': tag_id,
                'name': name,
                'color': color,
                'widget_id': widget_id,
                'shortcut_id': shortcut_id,
                'room_id': room_id,
                'created_at': str(created_at)
            }
        }, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Unexpected server error: {str(e)}'}, status=500)


@jwt_required
@agent_or_superadmin_required
def edit_tag(request, tag_id):
    if request.method != 'PATCH':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))

        name = data.get('name')
        color = data.get('color')
        shortcut_id = data.get('shortcut_id')
        room_id = data.get('room_id')
        new_widget_id = data.get('widget_id')  # New: Accept widget_id in request

        tag_collection = get_tag_collection()
        existing_tag = tag_collection.find_one({'tag_id': tag_id})
        if not existing_tag:
            return JsonResponse({'error': 'Tag not found'}, status=404)

        current_widget_id = existing_tag.get('widget_id')
        if not current_widget_id:
            return JsonResponse({'error': 'Tag is not associated with any widget'}, status=400)

        user = request.jwt_user
        role = user.get('role')
        admin_id = user.get('admin_id')

        # Permission check for current widget
        if role == 'agent':
            admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
            if not admin_doc:
                return JsonResponse({'error': 'Agent not found'}, status=404)

            assigned_widgets = admin_doc.get('assigned_widgets', [])
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]

            if current_widget_id not in assigned_widgets:
                return JsonResponse({'error': 'Unauthorized: Cannot edit tags from current widget'}, status=403)

            # If widget_id is being changed, check permission for new widget too
            if new_widget_id and new_widget_id != current_widget_id:
                if new_widget_id not in assigned_widgets:
                    return JsonResponse({'error': 'Unauthorized: Cannot move tag to target widget'}, status=403)

        # Determine the widget_id to use for validation
        target_widget_id = new_widget_id if new_widget_id else current_widget_id

        # Validate new widget exists (if widget_id is being changed)
        if new_widget_id and new_widget_id != current_widget_id:
            widget_collection = get_widget_collection()  # Assuming this function exists
            target_widget = widget_collection.find_one({'widget_id': new_widget_id})
            if not target_widget:
                return JsonResponse({'error': 'Target widget not found'}, status=404)

        # Check for duplicate tag name in target widget
        if name and tag_collection.find_one({
            'name': name, 
            'widget_id': target_widget_id, 
            'tag_id': {'$ne': tag_id}
        }):
            return JsonResponse({'error': f"Tag '{name}' already exists for the target widget"}, status=409)

        # Validate shortcut_id belongs to target widget
        if shortcut_id:
            shortcut = get_shortcut_collection().find_one({'shortcut_id': shortcut_id})
            if not shortcut or shortcut.get('widget_id') != target_widget_id:
                return JsonResponse({'error': 'Invalid shortcut_id or widget mismatch'}, status=403)

        # Validate room_id belongs to target widget
        if room_id:
            room = get_room_collection().find_one({'room_id': room_id})
            if not room or room.get('widget_id') != target_widget_id:
                return JsonResponse({'error': 'Invalid room_id or widget mismatch'}, status=403)

        # Prepare update fields
        update_fields = {
            'updated_at': timezone.now(),
        }
        
        # Add fields that are not None
        if name is not None:
            update_fields['name'] = name
        if color is not None:
            update_fields['color'] = color
        if shortcut_id is not None:
            update_fields['shortcut_id'] = shortcut_id
        if room_id is not None:
            update_fields['room_id'] = room_id
        if new_widget_id is not None:
            update_fields['widget_id'] = new_widget_id  # New: Update widget_id

        # Update the tag
        tag_collection.update_one({'tag_id': tag_id}, {'$set': update_fields})

        # Get updated tag
        updated_tag = tag_collection.find_one({'tag_id': tag_id})
        updated_tag['_id'] = str(updated_tag['_id'])
        updated_tag['created_at'] = str(updated_tag.get('created_at', ''))
        updated_tag['updated_at'] = str(updated_tag.get('updated_at', ''))

        return JsonResponse({
            'success': True,
            'message': 'Tag updated successfully',
            'tag': updated_tag
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Unexpected server error: {str(e)}'}, status=500)


@jwt_required
@agent_or_superadmin_required
def delete_tag(request, tag_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    tag_collection = get_tag_collection()
    shortcut_collection = get_shortcut_collection()
    room_collection = get_room_collection()
    # trigger_collection = get_trigger_collection()

    tag = tag_collection.find_one({'tag_id': tag_id})
    if not tag:
        return JsonResponse({'error': 'Tag not found'}, status=404)

    tag_name = tag.get('name')
    widget_id = tag.get('widget_id')

    # ✅ Agent role restriction
    user = request.jwt_user
    role = user.get('role')
    admin_id = user.get('admin_id')
    if role == 'agent':
        admin_doc = get_admin_collection().find_one({'admin_id': admin_id})
        assigned_widgets = admin_doc.get('assigned_widgets', [])
        if isinstance(assigned_widgets, str):
            assigned_widgets = [assigned_widgets]
        if widget_id not in assigned_widgets:
            return JsonResponse({'error': 'Unauthorized to delete this tag'}, status=403)

    # ✅ Remove tag reference from related collections
    if tag_name:
        shortcut_collection.update_many(
            {'tags': tag_name},
            {'$pull': {'tags': tag_name}}
        )
        room_collection.update_many(
            {'tags': tag_name},
            {'$pull': {'tags': tag_name}}
        )
        # trigger_collection.update_many(
        #     {'tags': tag_name},
        #     {'$pull': {'tags': tag_name}}
        # )

    # ✅ Finally delete tag
    tag_collection.delete_one({'tag_id': tag_id})

    return JsonResponse({'success': True, 'message': 'Tag and its references deleted successfully'})


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



class PatchTriggerAPIView(APIView):
    authentication_classes = [JWTAuthentication]

    def patch(self, request, trigger_id):
        widget_id = request.data.get('widget_id')
        if not widget_id:
            return Response({'error': 'widget_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = request.user
            role = request.user.get('role')
            admin_id = user.get('admin_id')

            # 🔍 Dynamically fetch assigned_widgets for agents
            if role == 'agent':
                user_record = get_admin_collection().find_one({'admin_id': admin_id})
                assigned_widgets = user_record.get('assigned_widgets', []) if user_record else []
                if isinstance(assigned_widgets, str):
                    assigned_widgets = [assigned_widgets]

                if widget_id not in assigned_widgets:
                    return Response({'error': 'Unauthorized: Not assigned to this widget'}, status=status.HTTP_403_FORBIDDEN)



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


# @api_view(['PATCH'])
# @jwt_required
# def update_trigger_message(request, trigger_id):
#     # user = request.jwt_user
#     widget_id = request.data.get('widget_id')
    
#     if not widget_id:
#         return Response({'error': 'widget_id is required'}, status=400)

#     # ✅ Role-based widget access: agent must be assigned, superadmin allowed
#     if not is_agent_assigned_to_widget(request, widget_id):
#         return Response({'error': 'Unauthorized: Not assigned to this widget'}, status=403)

#     collection = get_trigger_collection()
#     update_fields = {}

#     # Optional fields
#     if 'message' in request.data:
#         update_fields['message'] = request.data['message']

#     if 'name' in request.data:
#         update_fields['name'] = request.data['name']

#     if 'is_active' in request.data:
#         if not isinstance(request.data['is_active'], bool):
#             return Response({'error': 'is_active must be a boolean'}, status=400)
#         update_fields['is_active'] = request.data['is_active']

#     if 'suggested_replies' in request.data:
#         replies = request.data['suggested_replies']
#         if not isinstance(replies, list):
#             return Response({'error': 'suggested_replies must be a list'}, status=400)
#         update_fields['suggested_replies'] = replies

#     if 'order' in request.data:
#         order = request.data['order']
#         if not isinstance(order, int) or order <= 0:
#             return Response({'error': 'order must be a positive integer'}, status=400)
#         update_fields['order'] = order

#     if not update_fields:
#         return Response({'error': 'No valid fields provided to update'}, status=400)

#     update_fields['updated_at'] = timezone.now()

#     result = collection.update_one(
#         {'trigger_id': trigger_id, 'widget_id': widget_id},
#         {'$set': update_fields}
#     )

#     if result.matched_count == 0:
#         return Response({'error': 'Trigger not found or widget_id mismatch'}, status=404)

#     return Response({
#         'success': True,
#         'message': 'Trigger updated successfully',
#         'updated_fields': list(update_fields.keys())
#     })



from wish_bot.db import get_widget_collection
@jwt_required
def get_triggers_api(request):
    user = request.jwt_user
    role = user.get("role")
    admin_id = user.get("admin_id")

    assigned_widgets = []

    if role == "agent":
        # 🔍 Fetch assigned_widgets from the database
        user_record = get_admin_collection().find_one({'admin_id': admin_id})
        if user_record:
            assigned_widgets = user_record.get('assigned_widgets', [])
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]

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
    admin_id = user.get("admin_id")

    assigned_widgets = []

    if role == "agent":
        # 🔍 Fetch assigned_widgets from the database
        user_record = get_admin_collection().find_one({'admin_id': admin_id})
        if user_record:
            assigned_widgets = user_record.get('assigned_widgets', [])
            if isinstance(assigned_widgets, str):
                assigned_widgets = [assigned_widgets]

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
