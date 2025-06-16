from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Plane, Pilot, Command


class PilotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pilot
        fields = ['id', 'name', 'created_at']


class PlaneSerializer(GeoFeatureModelSerializer):
    pilot = PilotSerializer(read_only=True)
    pilot_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = Plane
        geo_field = 'current_position'
        fields = [
            'id', 'name', 'pilot', 'pilot_id',
            'start_point', 'end_point', 'current_position',
            'created_at', 'updated_at'
        ]


class PlaneListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing planes"""
    pilot_name = serializers.CharField(source='pilot.name', read_only=True)
    
    class Meta:
        model = Plane
        fields = [
            'id', 'name', 'pilot_name', 
            'current_position', 'updated_at'
        ]


class CommandSerializer(serializers.ModelSerializer):
    plane_name = serializers.CharField(source='plane.name', read_only=True)
    
    class Meta:
        model = Command
        fields = [
            'id', 'plane', 'plane_name', 'target_location',
            'message', 'status', 'created_at', 'updated_at'
        ]


class CommandCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Command
        fields = ['plane', 'target_location', 'message']
        
    def create(self, validated_data):
        validated_data['status'] = 'pending'
        return super().create(validated_data)


class CommandUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Command
        fields = ['status']
        
    def validate_status(self, value):
        if value not in ['accepted', 'rejected']:
            raise serializers.ValidationError(
                "Status can only be 'accepted' or 'rejected'"
            )
        return value 