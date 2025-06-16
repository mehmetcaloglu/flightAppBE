"""
Movement Utilities
Math functions for plane movement calculations
"""

import math


def calculate_distance(lat1, lng1, lat2, lng2):
    """
    Calculate the distance between two coordinates (in meters)
    Uses the Haversine formula
    """
    R = 6371000  # Earth radius in meters
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat_rad = math.radians(lat2 - lat1)
    dlng_rad = math.radians(lng2 - lng1)
    
    a = (math.sin(dlat_rad / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * 
         math.sin(dlng_rad / 2) ** 2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c  # meters


def calculate_bearing(lat1, lng1, lat2, lng2):
    """
    Calculate the bearing (direction angle) between two points
    Result: 0-360 degrees (0=North, 90=East, 180=South, 270=West)
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlng_rad = math.radians(lng2 - lng1)
    
    y = math.sin(dlng_rad) * math.cos(lat2_rad)
    x = (math.cos(lat1_rad) * math.sin(lat2_rad) - 
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlng_rad))
    
    bearing_rad = math.atan2(y, x)
    bearing_deg = math.degrees(bearing_rad)
    
    # normalize to 0-360 degrees
    return (bearing_deg + 360) % 360


def move_distance_with_bearing(lat, lng, distance_meters, bearing_degrees):
    """
    Calculate the new coordinate from a specific point, distance, and direction
    
    """
    R = 6371000  # Earth radius in meters
    
    lat_rad = math.radians(lat)
    lng_rad = math.radians(lng)
    bearing_rad = math.radians(bearing_degrees)
    
    # Spherical trigonometry
    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(distance_meters / R) +
        math.cos(lat_rad) * math.sin(distance_meters / R) * math.cos(bearing_rad)
    )
    
    new_lng_rad = lng_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(distance_meters / R) * math.cos(lat_rad),
        math.cos(distance_meters / R) - math.sin(lat_rad) * math.sin(new_lat_rad)
    )
    
    return math.degrees(new_lat_rad), math.degrees(new_lng_rad)


def move_towards_target(current_lat, current_lng, target_lat, target_lng, distance_meters):
    """
    Move towards the target with a certain distance from the current position
    If the remaining distance is less than the movement distance, go directly to the target
    """
    # remaining distance to the target
    remaining_distance = calculate_distance(current_lat, current_lng, target_lat, target_lng)
    
    # if the remaining distance is less than the movement distance, go directly to the target
    if remaining_distance <= distance_meters:
        return target_lat, target_lng, True
    
    # normal movement
    bearing = calculate_bearing(current_lat, current_lng, target_lat, target_lng)
    new_lat, new_lng = move_distance_with_bearing(current_lat, current_lng, distance_meters, bearing)
    
    return new_lat, new_lng, False
