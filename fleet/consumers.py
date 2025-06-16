import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db import connection
from .movement_utils import calculate_distance


class PlanePositionsConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Radius filtering
        self.lat = None
        self.lng = None
        self.radius = None
        # Bounding box filtering
        self.min_lat = None
        self.max_lat = None
        self.min_lng = None
        self.max_lng = None
        self.is_sending = False
        self.send_task = None

    async def connect(self):
        await self.accept()
        
        query_string = self.scope.get('query_string', b'').decode()
        params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
        
        # radius filter parameters
        try:
            if 'lat' in params and 'lng' in params and 'radius' in params:
                self.lat = float(params.get('lat'))
                self.lng = float(params.get('lng'))
                self.radius = float(params.get('radius'))
        except (ValueError, TypeError):
            self.lat = None
            self.lng = None
            self.radius = None
        
        # bounding box filter parameters
        try:
            if all(p in params for p in ['min_lat', 'max_lat', 'min_lng', 'max_lng']):
                self.min_lat = float(params.get('min_lat'))
                self.max_lat = float(params.get('max_lat'))
                self.min_lng = float(params.get('min_lng'))
                self.max_lng = float(params.get('max_lng'))
        except (ValueError, TypeError):
            self.min_lat = None
            self.max_lat = None
            self.min_lng = None
            self.max_lng = None
        
        # determine filter type
        filter_type = None
        filter_info = {}
        
        if self.lat and self.lng and self.radius:
            filter_type = 'radius'
            filter_info = {
                'type': 'radius',
                'lat': self.lat,
                'lng': self.lng,
                'radius': self.radius
            }
        elif self.min_lat and self.max_lat and self.min_lng and self.max_lng:
            filter_type = 'bounding_box'
            filter_info = {
                'type': 'bounding_box',
                'min_lat': self.min_lat,
                'max_lat': self.max_lat,
                'min_lng': self.min_lng,
                'max_lng': self.max_lng
            }
        
        # send connection established message
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'WebSocket connection established',
            'filters': filter_info
        }))
        
        # start periodic data sending
        self.is_sending = True
        self.send_task = asyncio.create_task(self.send_positions_periodically())
    
    async def disconnect(self, close_code):
        self.is_sending = False
        if self.send_task:
            self.send_task.cancel()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'update_filters':
                # update filters
                # radius filter check
                if 'lat' in data and 'lng' in data and 'radius' in data:
                    try:
                        self.lat = float(data.get('lat', 0))
                        self.lng = float(data.get('lng', 0))
                        self.radius = float(data.get('radius', 0))
                        # clear bounding box
                        self.min_lat = self.max_lat = self.min_lng = self.max_lng = None
                        
                        await self.send(text_data=json.dumps({
                            'type': 'filters_updated',
                            'message': 'Radius filter updated',
                            'filters': {
                                'type': 'radius',
                                'lat': self.lat,
                                'lng': self.lng,
                                'radius': self.radius
                            }
                        }))
                    except (ValueError, TypeError):
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': 'Invalid radius filter parameters'
                        }))
                
                # bounding box filter check
                elif all(p in data for p in ['min_lat', 'max_lat', 'min_lng', 'max_lng']):
                    try:
                        self.min_lat = float(data.get('min_lat'))
                        self.max_lat = float(data.get('max_lat'))
                        self.min_lng = float(data.get('min_lng'))
                        self.max_lng = float(data.get('max_lng'))
                        # clear radius
                        self.lat = self.lng = self.radius = None
                        
                        await self.send(text_data=json.dumps({
                            'type': 'filters_updated',
                            'message': 'Bounding box filter updated',
                            'filters': {
                                'type': 'bounding_box',
                                'min_lat': self.min_lat,
                                'max_lat': self.max_lat,
                                'min_lng': self.min_lng,
                                'max_lng': self.max_lng
                            }
                        }))
                    except (ValueError, TypeError):
                        await self.send(text_data=json.dumps({
                            'type': 'error',
                            'message': 'Invalid bounding box filter parameters'
                        }))
                
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Invalid filter format'
                    }))
            
            elif message_type == 'clear_filters':
                # clear filters
                self.lat = self.lng = self.radius = None
                self.min_lat = self.max_lat = self.min_lng = self.max_lng = None
                
                await self.send(text_data=json.dumps({
                    'type': 'filters_cleared',
                    'message': 'Filters cleared'
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON format'
            }))

    async def send_positions_periodically(self):
        """Send plane positions every 2 seconds - Dynamic Sleep"""
        TARGET_INTERVAL = 2.0  # seconds
        
        while self.is_sending:
            try:
                start_time = asyncio.get_event_loop().time()
                
                # get plane positions
                positions_data = await self.get_filtered_positions()
                
                # send to frontend
                await self.send(text_data=json.dumps({
                    'type': 'positions_update',
                    'data': positions_data,
                    'timestamp': int(start_time)
                }))
                
                # calculate elapsed time
                elapsed_time = asyncio.get_event_loop().time() - start_time
                sleep_time = TARGET_INTERVAL - elapsed_time
                
                # if process takes more than 2 seconds, sleep
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                # if process takes too long, warn
                elif elapsed_time > TARGET_INTERVAL + 0.5:  #0.5s tolerance
                    print(f"Sending plane positions to frontend is slow: {elapsed_time:.3f}s (target: {TARGET_INTERVAL}s)")
                
            except Exception as e:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': f'Data sending error: {str(e)}'
                }))
                break

    @database_sync_to_async
    def get_filtered_positions(self):
        """Get filtered plane positions - read from memory"""
        from .movement_manager import movement_manager
        from .models import Plane
        
        # get positions from MovementManager
        positions_with_heading = movement_manager.get_positions_with_heading()
        
        # get plane information from database
        plane_info = {}
        planes_in_db = Plane.objects.select_related('pilot').all()
        for plane in planes_in_db:
            plane_info[plane.id] = {
                'name': plane.name,
                'pilot_name': plane.pilot.name if plane.pilot else 'Pilot Yok'
            }
        
        filter_info = None
        planes = []
        
        # process positions in memory
        for plane_id, pos in positions_with_heading.items():
            lat = pos['current_lat']
            lng = pos['current_lng']
            heading = pos['heading']
            is_going_to_end = pos['is_going_to_end']
            
            # apply filter
            skip_plane = False
            
            # radius filter
            if self.lat and self.lng and self.radius:
                distance = calculate_distance(lat, lng, self.lat, self.lng)
                if distance > self.radius * 1000:  # in meters
                    skip_plane = True
                
                if not filter_info:
                    filter_info = {
                        'type': 'radius',
                        'lat': self.lat,
                        'lng': self.lng,
                        'radius': self.radius
                    }
            
            # bounding box filter
            elif self.min_lat and self.max_lat and self.min_lng and self.max_lng:
                if not (self.min_lat <= lat <= self.max_lat and self.min_lng <= lng <= self.max_lng):
                    skip_plane = True
                
                if not filter_info:
                    filter_info = {
                        'type': 'bounding_box',
                        'min_lat': self.min_lat,
                        'max_lat': self.max_lat,
                        'min_lng': self.min_lng,
                        'max_lng': self.max_lng
                    }
            
            # skip plane
            if skip_plane:
                continue
            
            # get plane information
            info = plane_info.get(plane_id, {'name': f'Plane {plane_id}', 'pilot_name': 'Pilot Yok'})
            
            # Format: [id, name, pilot, lng, lat, heading]
            planes.append([plane_id, info['name'], info['pilot_name'], lng, lat, heading])
        
        # sort by id
        planes.sort(key=lambda x: x[0])
        
        return {
            'planes': planes,
            'count': len(planes),
            'filters': filter_info
        }


class PilotCommandConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for pilot command notifications.
    - Each pilot connects and authenticates itself.
    - Backend sends special notifications to the relevant pilot.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pilot_name = None
        self.pilot_group_name = None

    async def connect(self):
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connection established. Please authenticate yourself with your pilot name.'
        }))

    async def disconnect(self, close_code):
        if self.pilot_group_name:
            await self.channel_layer.group_discard(
                self.pilot_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'authenticate':
                await self.authenticate_pilot(data)
            elif self.pilot_name:
                # only authenticated pilots can do other actions
                if message_type == 'get_pending_commands':
                    await self.send_pending_commands()
                else:
                    await self.send_error("Unknown command type.")
            else:
                await self.send_error("Please authenticate yourself first.")
        
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format.")
        except Exception as e:
            await self.send_error(f"An error occurred: {str(e)}")

    # WebSocket logic
    async def authenticate_pilot(self, data):
        pilot_name = data.get('pilot_name')
        if not pilot_name:
            await self.send_error("Pilot name is missing.")
            return

        pilot, plane = await self.get_pilot_and_plane(pilot_name)
        if pilot:
            self.pilot_name = pilot_name
            self.pilot_group_name = f"pilot_{self.pilot_name}"
            
            # Gruba ekle
            await self.channel_layer.group_add(
                self.pilot_group_name,
                self.channel_name
            )
            
            await self.send(text_data=json.dumps({
                'type': 'authenticated',
                'message': f"Pilot {self.pilot_name} authenticated successfully.",
                'pilot': self.pilot_name,
                'plane_id': plane.id if plane else None,
                'plane_name': plane.name if plane else None,
            }))
            
            # send pending commands immediately
            await self.send_pending_commands()
        else:
            await self.send_error(f"Pilot not found: {pilot_name}")

    async def send_pending_commands(self):
        pending_commands = await self.get_pending_commands_for_pilot()
        await self.send(text_data=json.dumps({
            'type': 'pending_commands',
            'commands': pending_commands
        }))

    # Handler for group messages (from backend)
    async def command_new(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_command',
            'command': event['command']
        }))

    async def command_update(self, event):
        """Triggered when command status is updated"""
        await self.send(text_data=json.dumps({
            'type': 'command_status_update',
            'command': event['command']
        }))

    # Utility methods
    async def send_error(self, message):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))

    @database_sync_to_async
    def get_pilot_and_plane(self, pilot_name):
        """Get pilot and plane from database"""
        from .models import Pilot, Plane
        try:
            pilot = Pilot.objects.get(name=pilot_name)
            plane = Plane.objects.filter(pilot=pilot).first()
            return pilot, plane
        except Pilot.DoesNotExist:
            return None, None

    @database_sync_to_async
    def get_pending_commands_for_pilot(self):
        """Get pending commands for the pilot"""
        from .models import Command
        from .serializers import CommandSerializer
        
        commands = Command.objects.filter(
            plane__pilot__name=self.pilot_name,
            status='pending'
        ).order_by('created_at')
        
        return CommandSerializer(commands, many=True).data


class CommandStatusConsumer(AsyncWebsocketConsumer):
    """
    Broadcast all command status updates (accepted/rejected)
    to a general channel. Used for frontend notifications.
    """
    COMMAND_STATUS_GROUP = "command_status_updates"

    async def connect(self):
        # accept the incoming connection and add to the group
        await self.channel_layer.group_add(
            self.COMMAND_STATUS_GROUP,
            self.channel_name
        )
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Successfully connected to the command status channel.'
        }))

    async def disconnect(self, close_code):
        # remove from the group when the connection is closed
        await self.channel_layer.group_discard(
            self.COMMAND_STATUS_GROUP,
            self.channel_name
        )

    # handler for group messages (from backend)
    async def command_update(self, event):
        """
        command status update (from views.py)
        sends to the connected client.
        """
        await self.send(text_data=json.dumps({
            'type': 'command_status_update',
            'command': event['command']
        })) 