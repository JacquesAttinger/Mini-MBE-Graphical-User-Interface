import ezdxf
import math

def round_point(pt, decimals=6):
    """Round an (x, y) tuple to the specified number of decimals."""
    # Skip rounding for tiny geometries to avoid collapse
    if abs(pt[0]) < 0.001 or abs(pt[1]) < 0.001:
        return (pt[0], pt[1])
    return (round(pt[0], decimals), round(pt[1], decimals))

def generate_points_from_line(start, end, resolution=1.0, use_interpolation=True):
    """
    Interpolates points along a line from start to end.
    If use_interpolation is False, returns just the endpoints.
    """
    start = round_point(start)
    end = round_point(end)
    if not use_interpolation:
        return [start, end]
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= resolution:
        return [start, end]
    num_segments = math.ceil(length / resolution)
    points = []
    for i in range(num_segments + 1):
        t = i / num_segments
        x = start[0] + dx * t
        y = start[1] + dy * t
        points.append(round_point((x, y)))
    return points

def generate_points_from_circle(center, radius, resolution=1.0):
    """
    Generates points along the circumference of a circle.
    Returns a list of (x, y) tuples with the first point repeated at the end.
    """
    circumference = 2 * math.pi * radius
    num_points = max(3, math.ceil(circumference / resolution))
    points = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        points.append(round_point((x, y)))
    points.append(points[0])
    return points

def generate_points_from_arc(center, radius, start_angle, end_angle, resolution=1.0):
    """
    Generates points along an arc defined by center, radius, start_angle, and end_angle (in degrees).
    Returns a list of (x, y) tuples.
    """
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)
    if end_rad < start_rad:
        end_rad += 2 * math.pi
    arc_length = radius * (end_rad - start_rad)
    num_points = max(2, math.ceil(arc_length / resolution))
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        angle = start_rad + t * (end_rad - start_rad)
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        points.append(round_point((x, y)))
    return points

def get_dxf_units(doc):
    """Returns the scaling factor to convert DXF units to mm."""
    header = doc.header
    insunits = header.get("$INSUNITS", 4)  # Default to mm (4) if not specified

    unit_scales = {
        0: 1.0,          # Unitless → assume mm
        1: 25.4,         # Inches → mm
        2: 304.8,        # Feet → mm
        3: 1609344.0,    # Miles → mm
        4: 1.0,          # Millimeters (no scaling)
        5: 10.0,         # Centimeters → mm
        6: 1000.0,       # Meters → mm
        7: 1e6,          # Kilometers → mm
        8: 0.0000254,    # Microinches → mm
        9: 0.0254,       # Mils → mm
        10: 914.4,       # Yards → mm
        11: 1e-7,        # Angstroms → mm
        12: 1e-6,        # Nanometers → mm
        13: 0.001,       # Microns → mm (FIXED)
        14: 100.0,       # Decimeters → mm
        15: 10000.0,     # Dekameters → mm
        16: 100000.0,    # Hectometers → mm
        17: 1e12,        # Gigameters → mm
        18: 1.496e11,    # Astronomical → mm
        19: 9.461e15,    # Light Years → mm
        20: 3.086e16,   # Parsecs → mm
        21: 304.8006,   # US Survey Feet → mm
        22: 25.40005,    # US Survey Inch → mm
        23: 914.4018,    # US Survey Yard → mm
        24: 1609347.0,   # US Survey Mile → mm
    }
    
    return unit_scales.get(insunits, 1.0)  # Default to mm if unknown unit

def parse_dxf(file_path, resolution=1.0, use_interpolation=True, force_mm=True):
    """
    Reads a DXF file and extracts movement paths, optionally converting to mm.

    Parameters:
      file_path: Path to the DXF file.
      resolution: Maximum allowed linear distance between successive points.
      use_interpolation: If False, for straight segments only the endpoints are returned.
      force_mm: If True, converts all coordinates to mm (default: True).

    Returns:
      A list of paths. Each path is a list of (x, y) tuples in mm.
    """
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()

    # Get scaling factor if forcing mm
    scale = get_dxf_units(doc) if force_mm else 1.0
    paths = []

    for entity in msp:
        etype = entity.dxftype()
        if etype == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            start_2d = (start[0] * scale, start[1] * scale)  # Apply scaling
            end_2d = (end[0] * scale, end[1] * scale)
            pts = generate_points_from_line(start_2d, end_2d, resolution, use_interpolation)
            paths.append(pts)

        elif etype == 'LWPOLYLINE':
            points = [(x * scale, y * scale) for x, y in entity.get_points('xy')]  # Scale first
            
            # Close the polyline if not already closed
            if len(points) > 1 and points[0] != points[-1]:
                points.append(points[0])
            
            # Filter out near-identical points (anti-degenerate)
            clean_points = []
            for i, pt in enumerate(points):
                if i == 0 or math.dist(pt, points[i-1]) > 1e-6:  # 1nm threshold
                    clean_points.append(pt)
            
            # Generate segments
            if len(clean_points) >= 2:
                poly_points = []
                for i in range(len(clean_points) - 1):
                    seg_pts = generate_points_from_line(
                        clean_points[i], 
                        clean_points[i+1], 
                        resolution, 
                        use_interpolation
                    )
                    poly_points.extend(seg_pts)
                paths.append(poly_points)

        elif etype == 'CIRCLE':
            center = entity.dxf.center
            radius = entity.dxf.radius * scale  # Scale radius
            center_2d = (center[0] * scale, center[1] * scale)
            pts = generate_points_from_circle(center_2d, radius, resolution)
            paths.append(pts)

        elif etype == 'ARC':
            center = entity.dxf.center
            radius = entity.dxf.radius * scale
            start_angle = entity.dxf.start_angle
            end_angle = entity.dxf.end_angle
            center_2d = (center[0] * scale, center[1] * scale)
            pts = generate_points_from_arc(center_2d, radius, start_angle, end_angle, resolution)
            paths.append(pts)
    return paths

def generate_recipe_from_dxf(file_path, resolution=1.0, use_interpolation=True, scale=1.0, mirror=False, z_height=0.0):
    """Returns standardized format with both display and movement data"""
    paths = parse_dxf(file_path, resolution, use_interpolation)
    
    display_paths = []
    movement_vertices = []
    segment_boundaries = []
    
    for path in paths:
        # Convert path to display coordinates
        display_path = []
        movement_path = []
        
        for i in range(len(path)):
            x, y = path[i]
            x *= scale
            y *= scale
            if mirror:
                x = -x
            
            display_path.append((x, y))
            movement_path.append((x, y, z_height))
            
            # Mark segment boundaries (end of each original line)
            if i > 0:
                segment_boundaries.append(len(movement_vertices)-1)
        
        display_paths.append(display_path)
        movement_vertices.extend(movement_path)
    
    return {
        'display': {
            'paths': display_paths,
            'type': '2D'
        },
        'movement': {
            'vertices': movement_vertices,
            'segments': segment_boundaries,
            'type': '3D'
        },
        'metadata': {
            'original_path_count': len(paths),
            'scale': scale,
            'resolution': resolution
        }
    }
