import pytest
from PySide6.QtCore import QCoreApplication

from controllers.manipulator_manager import ManipulatorManager, MotionNeverStartedError


class DummyCtrl:
    def __init__(self, start_pos: float):
        self.pos = start_pos
        self._last_speed = None

    def motor_on(self):
        pass

    def move_absolute(self, position: float, speed: float):
        # Negative speeds are invalid
        if speed < 0:
            raise MotionNeverStartedError("Motion never started")
        self.pos = position
        self._last_speed = speed

    def wait_until_in_position(self, target: float):
        return True

    def _read_status(self):
        return 0

    def read_error_code(self):
        return 0


def test_cross_origin_move_uses_positive_speed():
    app = QCoreApplication.instance() or QCoreApplication([])
    mgr = ManipulatorManager(motion_logging=False)
    mgr.controllers = {
        'x': DummyCtrl(1.0),
        'y': DummyCtrl(0.0),
        'z': DummyCtrl(0.0),
    }
    start = (1.0, 0.0, 0.0)
    target = (-1.0, 0.0, 0.0)
    assert mgr._move_axes(start, target, 0.5)
    assert mgr.controllers['x']._last_speed == pytest.approx(0.5)
    assert mgr.controllers['x'].pos == -1.0


def test_small_delta_uses_full_speed():
    app = QCoreApplication.instance() or QCoreApplication([])
    mgr = ManipulatorManager(motion_logging=False)
    mgr.controllers = {
        'x': DummyCtrl(0.0),
        'y': DummyCtrl(0.0),
        'z': DummyCtrl(0.0),
    }
    start = (0.0, 0.0, 0.0)
    target = (0.1, 100.0, 0.0)
    assert mgr._move_axes(start, target, 0.01)
    assert mgr.controllers['x']._last_speed == pytest.approx(0.01)
    assert mgr.controllers['y']._last_speed == pytest.approx(0.01)
