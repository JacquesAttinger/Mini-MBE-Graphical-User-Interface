from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from matplotlib.collections import LineCollection
from PySide6.QtCore import Qt

class EnhancedPositionCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 6))
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        
        # Initialize variables
        self.current_position = (0, 0)
        self.position_marker = None
        self.dxf_geometry = None
        self.scale_factor = 1.0
        self.current_zoom = 5.0
        self.view_center = [0, 0]
        self.pan_start = None
        self.pan_sensitivity = 0.5
        self._path_lines = {'completed': None, 'upcoming': None}
        self._dxf_lines = []
        self._pos_text = None

        # Style and setup
        self.fig.patch.set_facecolor('#f0f0f0')
        self.ax.set_facecolor('#f8f8f8')
        self.setParent(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Connect events
        self.mpl_connect('button_press_event', self.on_press)
        self.mpl_connect('button_release_event', self.on_release)
        self.mpl_connect('motion_notify_event', self.on_motion)

        self.update_plot()

    # --- Panning Methods ---
    def on_press(self, event):
        """Store starting position for click-and-drag panning"""
        if event.button == 1 and event.inaxes:  # Left mouse button
            self.pan_start = (event.xdata, event.ydata)

    def on_release(self, event):
        """Clear pan start position"""
        self.pan_start = None

    def on_motion(self, event):
        """Handle click-and-drag panning"""
        if self.pan_start is None or not event.inaxes:
            return
            
        dx = (event.xdata - self.pan_start[0]) * self.pan_sensitivity
        dy = (event.ydata - self.pan_start[1]) * self.pan_sensitivity
        self.pan_view(-dx, -dy)  # Move view in opposite direction of drag
        self.pan_start = (event.xdata, event.ydata)

    def pan_view(self, dx, dy):
        """Move view center by specified deltas"""
        self.view_center[0] += dx
        self.view_center[1] += dy
        self.update_plot()

    def reset_view(self):
        """Reset view to center on origin"""
        self.view_center = [0, 0]
        self.update_plot()

    # --- Programmatic Pan Controls ---
    def pan_up(self, amount=1.0):
        self.pan_view(0, amount * self.current_zoom/5)

    def pan_down(self, amount=1.0):
        self.pan_view(0, -amount * self.current_zoom/5)

    def pan_left(self, amount=1.0):
        self.pan_view(-amount * self.current_zoom/5, 0)

    def pan_right(self, amount=1.0):
        self.pan_view(amount * self.current_zoom/5, 0)

    # --- Data Update Methods ---
    def update_position(self, x, y):
        """Update current position marker"""
        self.current_position = (x, y)
        self.update_plot()

    def update_dxf(self, geometry, scale_factor=1.0):
        """Handle the standardized format"""
        try:
            self.scale_factor = scale_factor
            
            # Clear existing
            for collection in self._dxf_lines:
                collection.remove()
            self._dxf_lines = []
            
            # Extract display paths
            if isinstance(geometry, dict):
                if 'display' in geometry:
                    display_data = geometry['display']['paths']
                elif 'vertices' in geometry:  # Backward compatibility
                    display_data = [[(v[0], v[1])] for v in geometry['vertices']]
                else:
                    raise ValueError("Invalid DXF data format")
            elif isinstance(geometry, list):
                display_data = geometry
            else:
                raise ValueError("Unsupported geometry type")
            
            # Create LineCollection for each original path
            for path in display_data:
                if len(path) < 2:
                    continue
                    
                segments = []
                for i in range(len(path)-1):
                    segments.append([path[i], path[i+1]])
                
                lc = LineCollection(
                    segments,
                    colors='blue',
                    linewidths=0.5,  # Thinner lines for small features
                    alpha=0.7,
                    zorder=5,
                    capstyle='round',  # Anti-aliasing for small lines
                    antialiased=True
                )
                self.ax.add_collection(lc)
                self._dxf_lines.append(lc)
            
            self.update_plot()
            
        except Exception as e:
            print(f"Canvas DXF error: {str(e)}")
            raise ValueError(f"Failed to display DXF: {str(e)}")
        
        self.current_zoom = max(0.01, 2 * self._calculate_dxf_bounds(geometry))  # Auto-zoom to fit
        self.update_plot()

    def update_plot(self, zoom_level=None):
        """Main plotting method with performance optimizations"""
        if zoom_level is not None:
            self.current_zoom = zoom_level

        self.ax.set_autoscale_on(False)  # Critical for performance
        
        # Calculate display parameters
        scale, unit = (1000.0, "µm") if self.current_zoom < 0.1 else (1.0, "mm")
        scaled_limit = self.current_zoom * scale
        
        # Set view limits
        self.ax.set_xlim(self.view_center[0] - scaled_limit, 
                        self.view_center[0] + scaled_limit)
        self.ax.set_ylim(self.view_center[1] - scaled_limit, 
                        self.view_center[1] + scaled_limit)

        # Configure axes
        self.ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.7)
        self.ax.set_title(f"Position Monitor (±{scaled_limit:.2f} {unit})", pad=20)
        
        # Update current position marker
        x, y = self.current_position
        x_disp = x * scale
        y_disp = y * scale
        
        if self.position_marker:
            self.position_marker.remove()
            
        self.position_marker = Circle(
            (x_disp, y_disp), 
            radius=scaled_limit/30, 
            color='r', 
            alpha=0.7, 
            zorder=10
        )
        self.ax.add_patch(self.position_marker)
        
        # Update position indicators
        for line in self.ax.lines:
            if hasattr(line, '_position_indicator'):
                line.remove()
                
        hline = self.ax.axhline(y_disp, color='r', linestyle='--', linewidth=0.8, alpha=0.5)
        vline = self.ax.axvline(x_disp, color='r', linestyle='--', linewidth=0.8, alpha=0.5)
        hline._position_indicator = True
        vline._position_indicator = True
        
        # Update position text
        if self._pos_text:
            self._pos_text.remove()
        self._pos_text = self.ax.text(
            x_disp, y_disp, 
            f"({x_disp:.2f}, {y_disp:.2f}) {unit}", 
            color='darkred', 
            fontsize=9, 
            ha='center', 
            va='bottom',
            zorder=11
        )
        
        self.fig.canvas.draw_idle()

    def draw_path_progress(self, current_index, vertices, segment_boundaries):
        """Only connect points that were originally connected"""
        if not hasattr(self, '_path_lines'):
            self._path_lines = {'completed': [], 'upcoming': []}
        
        # Clear old lines
        for line in self._path_lines['completed'] + self._path_lines['upcoming']:
            if line in self.ax.lines:
                line.remove()
        self._path_lines = {'completed': [], 'upcoming': []}
        
        if not vertices or current_index < 0:
            return
        
        # Find current segment
        current_segment = 0
        while (current_segment < len(segment_boundaries) and 
            current_index > segment_boundaries[current_segment]):
            current_segment += 1
        
        # Draw completed segments (green)
        if current_segment > 0:
            start_idx = 0
            for seg_end in segment_boundaries[:current_segment]:
                seg_verts = vertices[start_idx:seg_end+1]
                if len(seg_verts) > 1:
                    line = self.ax.plot(
                        [v[0] for v in seg_verts],
                        [v[1] for v in seg_verts],
                        'g-', alpha=0.5, linewidth=2, zorder=6
                    )[0]
                    self._path_lines['completed'].append(line)
                start_idx = seg_end + 1
        
        # Draw current segment (yellow)
        if current_segment < len(segment_boundaries):
            seg_start = 0 if current_segment == 0 else segment_boundaries[current_segment-1]+1
            seg_end = segment_boundaries[current_segment]
            current_seg_verts = vertices[seg_start:min(current_index, seg_end)+1]
            if len(current_seg_verts) > 1:
                line = self.ax.plot(
                    [v[0] for v in current_seg_verts],
                    [v[1] for v in current_seg_verts],
                    'y-', alpha=0.7, linewidth=2, zorder=7
                )[0]
                self._path_lines['completed'].append(line)
        
        # Draw upcoming segments (blue)
        if current_segment < len(segment_boundaries):
            # Remaining in current segment
            if current_index < segment_boundaries[current_segment]:
                remaining_verts = vertices[current_index:segment_boundaries[current_segment]+1]
                if len(remaining_verts) > 1:
                    line = self.ax.plot(
                        [v[0] for v in remaining_verts],
                        [v[1] for v in remaining_verts],
                        'b--', alpha=0.3, linewidth=1, zorder=6
                    )[0]
                    self._path_lines['upcoming'].append(line)
            
            # Future segments
            for seg_end in segment_boundaries[current_segment+1:]:
                seg_start = segment_boundaries[current_segment]+1
                seg_verts = vertices[seg_start:seg_end+1]
                if len(seg_verts) > 1:
                    line = self.ax.plot(
                        [v[0] for v in seg_verts],
                        [v[1] for v in seg_verts],
                        'b--', alpha=0.3, linewidth=1, zorder=6
                    )[0]
                    self._path_lines['upcoming'].append(line)
                current_segment += 1
        
        self.fig.canvas.draw_idle()

    def _calculate_dxf_bounds(self, geometry):
        if isinstance(geometry, dict) and 'display' in geometry:
            paths = geometry['display']['paths']
        else:
            paths = geometry
        
        all_points = [pt for path in paths for pt in path]
        if not all_points:
            return 0.01  # Default zoom if no geometry

        xs, ys = zip(*all_points)
        return max(max(xs) - min(xs), max(ys) - min(ys)) * 1.1  # 10% padding
