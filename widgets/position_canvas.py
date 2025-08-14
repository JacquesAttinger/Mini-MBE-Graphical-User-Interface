from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from matplotlib.collections import LineCollection
from PySide6.QtCore import Qt
import logging

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
        self.mpl_connect('scroll_event', self.on_scroll)

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

    # --- Zoom Controls ---
    def on_scroll(self, event):
        """Handle mouse wheel zooming"""
        if event.step > 0:
            self.zoom_in()
        elif event.step < 0:
            self.zoom_out()

    def zoom_in(self):
        self.zoom(0.8)

    def zoom_out(self):
        self.zoom(1.25)

    def zoom(self, factor):
        """Scale the current zoom level by *factor*"""
        self.current_zoom = max(0.001, self.current_zoom * factor)
        self.update_plot()

    def center_on_position(self):
        """Center the view on the current manipulator position"""
        scale = 1000.0 if self.current_zoom < 0.1 else 1.0
        x_disp = self.current_position[0] * scale
        y_disp = self.current_position[1] * scale
        self.view_center = [x_disp, y_disp]
        self.update_plot()

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
            logging.error("Canvas DXF error: %s", e)
            raise ValueError(f"Failed to display DXF: {e}")
        
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
