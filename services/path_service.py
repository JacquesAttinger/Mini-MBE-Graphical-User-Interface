import numpy as np
import math
from PySide6.QtCore import QObject, Signal, QTimer

# ----------------------------------------------------------------------
# Physical Velocity Constraints
# ----------------------------------------------------------------------
MIN_AXIS_VELOCITY = 1e-4  # mm/s
MAX_AXIS_VELOCITY = 1.0    # mm/s
VELOCITY_THRESHOLD = 5e-5  # Threshold for rounding to zero

class PathService(QObject):
    progress_updated = Signal(float, float, float)  # x, y, z
    path_completed = Signal()
    paused = Signal()
    segment_started = Signal(int)  # segment index

    def __init__(self, controllers):
        super().__init__()
        self.controllers = controllers  # Dictionary of axis controllers
        self.current_path = []
        self.current_index = 0
        self.is_paused = False
        self.is_running = False
        self.timer = QTimer()
        self.timer.timeout.connect(self._process_next_point)
        self.path_metadata = {}

    def load_path(self, path_data):
        self.current_path = path_data['vertices']
        self.segment_boundaries = path_data.get('segments', [])
        self.current_index = 0

    def embark(self):
        if not self.current_path:
            return
        
        self.is_running = True
        self.is_paused = False
        self.timer.start(50)  # 20Hz update rate

    def pause(self):
        self.is_paused = True
        self.timer.stop()
        self.paused.emit()

    def resume(self):
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.timer.start(50)

    def validate_velocity(self, velocity):
        """Ensure the requested velocity is physically achievable."""
        if velocity < MIN_AXIS_VELOCITY:
            raise ValueError(f"Velocity too slow (min: {MIN_AXIS_VELOCITY} mm/s)")
        
        # Theoretical max: sqrt(3) * MAX_AXIS_VELOCITY when all 3 axes move at max speed
        theoretical_max = math.sqrt(3) * MAX_AXIS_VELOCITY
        if velocity > theoretical_max:
            raise ValueError(
                f"Requested velocity ({velocity} mm/s) exceeds maximum possible ({theoretical_max:.3f} mm/s) "
                f"for diagonal moves (all axes at {MAX_AXIS_VELOCITY} mm/s)"
            )
    
    def adjust_axis_velocity(self, v):
        """Adjust individual axis velocity according to constraints"""
        if abs(v) < VELOCITY_THRESHOLD:
            return 0
        elif abs(v) < MIN_AXIS_VELOCITY:
            return math.copysign(MIN_AXIS_VELOCITY, v)
        elif abs(v) > MAX_AXIS_VELOCITY:
            return math.copysign(MAX_AXIS_VELOCITY, v)
        return v
    
    def calculate_velocity_components(self, start_pos, end_pos, total_velocity):
        """
        Calculate velocity components for each axis with physical constraints
        """
        # Validate total velocity first
        self.validate_velocity(total_velocity)
        
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        dz = end_pos[2] - start_pos[2]
        
        distance = math.sqrt(dx**2 + dy**2 + dz**2)
        if distance == 0:
            return (0, 0, 0)
            
        # Calculate direction unit vector
        ux = dx / distance
        uy = dy / distance
        uz = dz / distance
        
        # Scale by total velocity and apply constraints
        vx = self.adjust_axis_velocity(ux * total_velocity)
        vy = self.adjust_axis_velocity(uy * total_velocity)
        vz = self.adjust_axis_velocity(uz * total_velocity)
        
        # Re-normalize if any components were clamped
        actual_velocity = math.sqrt(vx**2 + vy**2 + vz**2)
        if actual_velocity > 0 and actual_velocity < total_velocity:
            scale = total_velocity / actual_velocity
            vx = self.adjust_axis_velocity(vx * scale)
            vy = self.adjust_axis_velocity(vy * scale)
            vz = self.adjust_axis_velocity(vz * scale)
        
        return (vx, vy, vz)

    def point_trajectory(self, start_pos, end_pos, velocity):
        """
        Move in straight line with velocity constraints
        """
        try:
            vx, vy, vz = self.calculate_velocity_components(start_pos, end_pos, velocity)
        except ValueError as e:
            print(f"Velocity error: {e}")
            return False
            
        # Calculate move time based on longest axis
        dx = abs(end_pos[0] - start_pos[0])
        dy = abs(end_pos[1] - start_pos[1])
        dz = abs(end_pos[2] - start_pos[2])
        
        times = {}
        if vx != 0:
            times['X'] = dx / abs(vx)
        if vy != 0:
            times['Y'] = dy / abs(vy)
        if vz != 0:
            times['Z'] = dz / abs(vz)
        
        if not times:  # No movement needed
            return True
            
        limit_axis = max(times, key = times.get)
        total_time = times[limit_axis]

        vs = {'X': vx, 'Y': vy, 'Z': vz}
        end_pos = {'X': end_pos[0], 'Y': end_pos[1], 'Z': end_pos[2]}
        return


    def _process_next_point(self):
        if self.is_paused or self.current_index >= len(self.current_path):
            return
            
        target = self.current_path[self.current_index]

        # Get current position from controllers
        try:
            current_pos = (
                float(self.controllers['X'].read_position()),
                float(self.controllers['Y'].read_position()),
                float(self.controllers['Z'].read_position())
            )
        except Exception as e:
            print(f"Position read error: {e}")
            self.pause()
            return

        # Calculate direction vector
        dx = target[0] - current_pos[0]
        dy = target[1] - current_pos[1]
        dz = target[2] - current_pos[2]
        distance = np.linalg.norm([dx, dy, dz])
        
        self.point_trajectory(current_pos, target, velocity=1e-3)

        self.progress_updated.emit(*target)
        self.current_index += 1
        
        if self.current_index >= len(self.current_path):
            self.timer.stop()
            self.path_completed.emit()

    def get_current_segment(self):
        if self.current_index == 0:
            return 0
        return min(self.current_index - 1, len(self.current_path) - 1)
    def get_progress(self):
        if not self.current_path:
            return 0
        return self.current_index / len(self.current_path)

