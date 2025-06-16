"""
Movement Manager
Uçak hareket yönetimi ana sistemi
"""

import threading
import time
import logging
from typing import Dict, Tuple, Optional
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from .models import Plane
from .movement_utils import calculate_bearing, move_towards_target


logger = logging.getLogger(__name__)


class MovementManager:
    """
    Aircraft movement management system
    - Keeps current positions in memory
    - Updates positions every 2 seconds
    - Saves to database every 2 minutes
    """
    
    def __init__(self):
        self.running = False
        self.movement_thread = None
        self.db_save_thread = None
        
        # current positions in memory
        # {plane_id: {'current_lat': float, 'current_lng': float, 'target_lat': float, 'target_lng': float, 'is_going_to_end': bool}}
        self.plane_positions: Dict[int, Dict] = {}
        
        # thread safety lock
        self.positions_lock = threading.Lock()
        
        # movement parameters
        self.MOVEMENT_DISTANCE = 600  # meters
        self.MOVEMENT_INTERVAL = 2  # seconds
        self.DB_SAVE_INTERVAL = 120  # seconds (2 minutes)
        
        logger.info("MovementManager initialized")
    
    def load_planes_from_db(self):
        """Load planes from database"""
        try:
            planes = Plane.objects.all()
            with self.positions_lock:
                self.plane_positions.clear()
                
                for plane in planes:
                    self.plane_positions[plane.id] = {
                        'current_lat': float(plane.current_position.y),  # PointField.y = latitude
                        'current_lng': float(plane.current_position.x),  # PointField.x = longitude
                        'target_lat': float(plane.end_point.y) if plane.is_going_to_end else float(plane.start_point.y),
                        'target_lng': float(plane.end_point.x) if plane.is_going_to_end else float(plane.start_point.x),
                        'is_going_to_end': plane.is_going_to_end,
                        'last_updated': time.time()
                    }
            
            logger.info(f"{len(self.plane_positions)} planes loaded to memory")
            
        except Exception as e:
            logger.error(f"Error: planes not loaded: {e}")
    
    def get_plane_position(self, plane_id: int) -> Optional[Dict]:
        with self.positions_lock:
            return self.plane_positions.get(plane_id)
    
    def get_all_positions(self) -> Dict[int, Dict]:
        with self.positions_lock:
            # return a copy, original dict is not modified
            return dict(self.plane_positions)
    
    def get_positions_with_heading(self) -> Dict[int, Dict]:
        with self.positions_lock:
            result = {}
            
            for plane_id, pos in self.plane_positions.items():
                # calculate heading
                heading = calculate_bearing(
                    pos['current_lat'], pos['current_lng'],
                    pos['target_lat'], pos['target_lng']
                )
                
                result[plane_id] = {
                    'current_lat': pos['current_lat'],
                    'current_lng': pos['current_lng'],
                    'is_going_to_end': pos['is_going_to_end'],
                    'heading': round(heading, 1),
                    'last_updated': pos['last_updated']
                }
            
            return result
    
    def update_positions(self):
        """Update the positions of all planes"""
        if not self.plane_positions:
            return
        
        updated_count = 0
        
        with self.positions_lock:
            current_time = time.time()
            
            for plane_id, pos in list(self.plane_positions.items()):
                try:
                    # move from current position to target
                    new_lat, new_lng, reached_target = move_towards_target(
                        pos['current_lat'], pos['current_lng'],
                        pos['target_lat'], pos['target_lng'],
                        self.MOVEMENT_DISTANCE
                    )
                    
                    # update position
                    pos['current_lat'] = new_lat
                    pos['current_lng'] = new_lng
                    pos['last_updated'] = current_time
                    
                    # if reached the target, change direction
                    if reached_target:
                        pos['is_going_to_end'] = not pos['is_going_to_end']
                        
                        # set new target
                        if pos['is_going_to_end']:
                            # now going to end
                            try:
                                plane = Plane.objects.get(id=plane_id)
                                pos['target_lat'] = float(plane.end_point.y)
                                pos['target_lng'] = float(plane.end_point.x)
                            except ObjectDoesNotExist:
                                logger.warning(f"Plane {plane_id} not found, removing from memory")
                                del self.plane_positions[plane_id]
                                continue
                        else:
                            # now going to start
                            try:
                                plane = Plane.objects.get(id=plane_id)
                                pos['target_lat'] = float(plane.start_point.y)
                                pos['target_lng'] = float(plane.start_point.x)
                            except ObjectDoesNotExist:
                                logger.warning(f"Plane {plane_id} not found, removing from memory")
                                del self.plane_positions[plane_id]
                                continue
                        
                        logger.debug(f" Plane {plane_id} reached target, direction changed: {'end' if pos['is_going_to_end'] else 'start'}")
                    
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Error: plane {plane_id} not updated: {e}")
        
        if updated_count > 0:
            logger.debug(f"{updated_count} planes updated")
    
    def save_to_database(self):
        """Save positions in memory to database"""
        if not self.plane_positions:
            return
        
        saved_count = 0
        
        try:
            with transaction.atomic():
                with self.positions_lock:
                    for plane_id, pos in self.plane_positions.items():
                        try:
                            from django.contrib.gis.geos import Point
                            plane = Plane.objects.get(id=plane_id)
                            plane.current_position = Point(pos['current_lng'], pos['current_lat'], srid=4326)
                            plane.is_going_to_end = pos['is_going_to_end']
                            plane.save(update_fields=['current_position', 'is_going_to_end'])
                            saved_count += 1
                            
                        except ObjectDoesNotExist:
                            logger.warning(f"Plane {plane_id} not found, removing from memory")
                            del self.plane_positions[plane_id]
                        except Exception as e:
                            logger.error(f"Error: plane {plane_id} not saved: {e}")
            
            logger.info(f"{saved_count} planes saved to database")
            
        except Exception as e:
            logger.error(f"Error: planes not saved to database: {e}")
    
    def movement_loop(self):
        """Main movement loop - runs every 2 seconds"""
        logger.info("Movement loop started")
        
        while self.running:
            try:
                start_time = time.time()
                
                # update positions
                self.update_positions()
                
                # calculate elapsed time and dynamic sleep
                elapsed_time = time.time() - start_time
                sleep_time = self.MOVEMENT_INTERVAL - elapsed_time
                
                # if process takes more than 2 seconds, sleep
                if sleep_time > 0:
                    time.sleep(sleep_time)
                # Performance warning
                elif elapsed_time > self.MOVEMENT_INTERVAL + 0.5:  # 0.5s tolerance
                    logger.warning(f" Calculating plane positions is slow: {elapsed_time:.3f}s (target: {self.MOVEMENT_INTERVAL}s)")
                
            except Exception as e:
                logger.error(f"Movement loop error: {e}")
                time.sleep(0.1)  # short sleep and continue
    
    def db_save_loop(self):
        """Database save loop (runs every 2 minutes)"""
        logger.info("Database save loop started")
        
        while self.running:
            try:
                time.sleep(self.DB_SAVE_INTERVAL)
                if self.running:  # if still running, save
                    self.save_to_database()
                    
            except Exception as e:
                logger.error(f"Database save loop error: {e}")
                time.sleep(10)  # short sleep and continue
    
    def start(self):
        """Start the movement system"""
        if self.running:
            logger.warning("MovementManager is already running")
            return
        
        logger.info("MovementManager is starting...")
        
        # load planes from database
        self.load_planes_from_db()
        
        # start threads
        self.running = True
        
        self.movement_thread = threading.Thread(target=self.movement_loop, daemon=True)
        self.movement_thread.start()
        
        self.db_save_thread = threading.Thread(target=self.db_save_loop, daemon=True)
        self.db_save_thread.start()
        
        logger.info("MovementManager started successfully")
    
    def stop(self):
        """Stop the movement system"""
        if not self.running:
            logger.warning("MovementManager is already stopped")
            return
        
        logger.info("MovementManager is stopping...")
        
        self.running = False
        
        # wait for threads to finish
        if self.movement_thread and self.movement_thread.is_alive():
            self.movement_thread.join(timeout=5)
        
        if self.db_save_thread and self.db_save_thread.is_alive():
            self.db_save_thread.join(timeout=5)
        
        # save one last time
        self.save_to_database()
        
        logger.info("MovementManager stopped successfully")
    
    def update_plane_target(self, plane_id: int, new_target_lat: float, new_target_lng: float):
        """Update the target of a specific plane immediately (when command is accepted)"""
        with self.positions_lock:
            if plane_id in self.plane_positions:
                plane_data = self.plane_positions[plane_id]
                
                # set new target
                plane_data['target_lat'] = new_target_lat
                plane_data['target_lng'] = new_target_lng
                
                logger.info(f"New target set for Plane {plane_id}: {new_target_lat}, {new_target_lng}")
                return True
            else:
                logger.warning(f"Target update failed: Plane {plane_id} not found in memory.")
                return False



# Global instance
movement_manager = MovementManager() 