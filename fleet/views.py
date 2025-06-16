from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import Distance
from django.db import connection
from .models import Plane, Pilot, Command
from .serializers import (
    PlaneSerializer, PlaneListSerializer, PilotSerializer,
    CommandSerializer, CommandCreateSerializer, CommandUpdateSerializer
)
from .movement_utils import calculate_distance


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10000  
    page_size_query_param = 'page_size'
    max_page_size = 10000


class PilotViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Pilot list and details ,read-only
    """
    queryset = Pilot.objects.all().order_by('name')
    serializer_class = PilotSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['name']
    search_fields = ['name']


class PlaneViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Plane list and details, read-only
    """
    queryset = Plane.objects.select_related('pilot').all()
    pagination_class = None  # disable pagination, show all planes
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['pilot__name']
    search_fields = ['name', 'pilot__name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return PlaneListSerializer
        return PlaneSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Query optimization - only necessary fields
        if self.action == 'list':
            queryset = queryset.only(
                'id', 'name', 'current_position', 'updated_at', 'pilot__name'
            )
        elif self.action == 'positions':
            queryset = queryset.only(
                'id', 'name', 'current_position', 'updated_at'
            )
        
        # Geographical filtering
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius')  # in km
        
        if lat and lng and radius:
            try:
                center = Point(float(lng), float(lat), srid=4326)
                distance = Distance(km=float(radius))
                queryset = queryset.filter(
                    current_position__distance_lte=(center, distance)
                )
            except (ValueError, TypeError):
                pass
        
        return queryset.order_by('name')
    
    @action(detail=False, methods=['get'])
    def positions(self, request):
        """
        Return only position information for all planes -read from memory
        """
        from .movement_manager import movement_manager
        
        # Geographical filtering parameters
        # Radius filtering
        lat = request.query_params.get('lat')
        lng = request.query_params.get('lng')
        radius = request.query_params.get('radius')  # in km
        
        # Bounding box filtering
        min_lat = request.query_params.get('min_lat')
        max_lat = request.query_params.get('max_lat')
        min_lng = request.query_params.get('min_lng')
        max_lng = request.query_params.get('max_lng')
        
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
        features = []
        
        # process positions in memory
        for plane_id, pos in positions_with_heading.items():
            plane_lat = pos['current_lat']
            plane_lng = pos['current_lng']
            heading = pos['heading']
            
            # apply filtering
            skip_plane = False
            
            # Radius filtering (priority)
            if lat and lng and radius:
                try:
                    lat_float = float(lat)
                    lng_float = float(lng)
                    radius_float = float(radius)
                    
                    distance = calculate_distance(plane_lat, plane_lng, lat_float, lng_float)
                    if distance > radius_float * 1000:  # km -> metre
                        skip_plane = True
                    
                    if not filter_info:
                        filter_info = {
                            'type': 'radius',
                            'lat': lat_float,
                            'lng': lng_float,
                            'radius_km': radius_float
                        }
                except (ValueError, TypeError):
                    pass  # invalid parameters, no filtering
            
            # Bounding box filtering
            elif min_lat and max_lat and min_lng and max_lng:
                try:
                    min_lat_float = float(min_lat)
                    max_lat_float = float(max_lat)
                    min_lng_float = float(min_lng)
                    max_lng_float = float(max_lng)
                    
                    if not (min_lat_float <= plane_lat <= max_lat_float and min_lng_float <= plane_lng <= max_lng_float):
                        skip_plane = True
                    
                    if not filter_info:
                        filter_info = {
                            'type': 'bounding_box',
                            'min_lat': min_lat_float,
                            'max_lat': max_lat_float,
                            'min_lng': min_lng_float,
                            'max_lng': max_lng_float
                        }
                except (ValueError, TypeError):
                    pass  # invalid parameters, no filtering
            
            # skip this plane
            if skip_plane:
                continue
            
            # get plane information
            info = plane_info.get(plane_id, {'name': f'Plane {plane_id}', 'pilot_name': 'Pilot Yok'})
            
            # Format: [id, name, pilot, lng, lat, heading]
            features.append([plane_id, info['name'], info['pilot_name'], plane_lng, plane_lat, heading])
        
        # sort by id
        features.sort(key=lambda x: x[0])
        
        return Response({
            'planes': features,  # [[id, plane_name, pilot_name, lng, lat, heading], ...]
            'count': len(features),
            'filters': filter_info
        })
    
    @action(detail=True, methods=['get'])
    def commands(self, request, pk=None):
        """
        List commands for a specific plane
        """
        plane = self.get_object()
        commands = Command.objects.filter(plane=plane).order_by('-created_at')
        
        page = self.paginate_queryset(commands)
        if page is not None:
            serializer = CommandSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = CommandSerializer(commands, many=True)
        return Response(serializer.data)


class CommandViewSet(viewsets.ModelViewSet):
    """
    Command management (CRUD)
    """
    queryset = Command.objects.select_related('plane', 'plane__pilot').all()
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'plane__name']
    search_fields = ['message', 'plane__name']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CommandCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return CommandUpdateSerializer
        return CommandSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # filtering by pilot (for mobile app)
        pilot_name = self.request.query_params.get('pilot')
        if pilot_name:
            queryset = queryset.filter(plane__pilot__name=pilot_name)
        
        return queryset.order_by('-created_at')
    
    def perform_update(self, serializer):
        """
        Special actions when command status is updated
        """
        command = serializer.save()
        
        # if command is accepted, update the plane's route
        if command.status == 'accepted':
            plane = command.plane
            plane.start_point = plane.current_position
            plane.end_point = command.target_location
            plane.save(update_fields=['start_point', 'end_point', 'updated_at'])
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        
        commands = self.get_queryset().filter(status='pending')
        
        page = self.paginate_queryset(commands)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(commands, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        
        command = self.get_object()
        if command.status != 'pending':
            return Response(
                {'error': 'Only pending commands can be accepted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        command.status = 'accepted'
        command.save()
        
        # 1. update MovementManager
        try:
            from .movement_manager import movement_manager
            movement_manager.update_plane_target(
                plane_id=command.plane.id,
                new_target_lat=command.target_location.y,
                new_target_lng=command.target_location.x
            )
        except Exception as e:
            print(f"HATA: MovementManager güncellenemedi: {e}")

        # 2. send notification to the general dashboard channel
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            group_name = "command_status_updates" # general group name
            
            message = {
                'type': 'command_update', # method in CommandStatusConsumer
                'command': self.get_serializer(command).data
            }
            
            async_to_sync(channel_layer.group_send)(group_name, message)
        except Exception as e:
            print(f"Error: WebSocket 'accept' notification not sent: {e}")

        serializer = self.get_serializer(command)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
       
        command = self.get_object()
        if command.status != 'pending':
            return Response(
                {'error': 'Only pending commands can be rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        command.status = 'rejected'
        command.save()
        
        # send notification to the general dashboard channel
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            group_name = "command_status_updates" # general group name
            
            message = {
                'type': 'command_update', # method in CommandStatusConsumer
                'command': self.get_serializer(command).data
            }
            
            async_to_sync(channel_layer.group_send)(group_name, message)
        except Exception as e:
            print(f"Error: WebSocket 'reject' notification not sent: {e}")
        
        serializer = self.get_serializer(command)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Send WebSocket notification to the pilot when a new command is created"""
        command = serializer.save() # status='pending' is already set in serializer
        
        # send notification to the pilot
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            #we need to re-serialize to get plane_name or etc.
            from .serializers import CommandSerializer 
            command_data = CommandSerializer(command).data

            channel_layer = get_channel_layer()
            pilot_name = command.plane.pilot.name
            group_name = f'pilot_{pilot_name}'
            
            #prepare message
            message = {
                'type': 'command_new',  # method in PilotCommandConsumer
                'command': command_data
            }
            
            # send to the group
            async_to_sync(channel_layer.group_send)(group_name, message)
            
        except Exception as e:
            print(f"Error: WebSocket notification not sent: {e}")
