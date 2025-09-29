"""Utilities for speed validation and clamping."""

import math

# ----------------------------------------------------------------------
# Physical speed constraints
# ----------------------------------------------------------------------
MIN_AXIS_SPEED = 1e-5  # mm/s
MAX_AXIS_SPEED = 1.0    # mm/s
SPEED_THRESHOLD = 5e-6  # Threshold for rounding to zero


def validate_speed(speed: float) -> None:
    """Ensure the requested speed is physically achievable."""
    if speed < MIN_AXIS_SPEED:
        raise ValueError(f"Speed too slow (min: {MIN_AXIS_SPEED} mm/s)")

    # Theoretical max: sqrt(3) * MAX_AXIS_SPEED when all 3 axes move at max speed
    theoretical_max = math.sqrt(3) * MAX_AXIS_SPEED
    if speed > theoretical_max:
        raise ValueError(
            f"Requested speed ({speed} mm/s) exceeds maximum possible ({theoretical_max:.3f} mm/s) "
            f"for diagonal moves (all axes at {MAX_AXIS_SPEED} mm/s)"
        )


def adjust_axis_speed(speed: float) -> float:
    """Clamp an individual axis speed according to constraints."""
    if abs(speed) < SPEED_THRESHOLD:
        return 0.0
    if abs(speed) < MIN_AXIS_SPEED:
        return math.copysign(MIN_AXIS_SPEED, speed)
    if abs(speed) > MAX_AXIS_SPEED:
        return math.copysign(MAX_AXIS_SPEED, speed)
    return speed
