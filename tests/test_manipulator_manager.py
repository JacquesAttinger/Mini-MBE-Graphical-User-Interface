import threading

import pytest
from PySide6.QtCore import QCoreApplication

from controllers.manipulator_manager import ManipulatorManager, MotionNeverStartedError
from utils.speed import MIN_AXIS_SPEED


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

    def read_position(self):
        return self.pos

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
    assert mgr.controllers['x']._last_speed == pytest.approx(MIN_AXIS_SPEED)
    assert mgr.controllers['y']._last_speed == pytest.approx(0.01)
    total = (
        mgr.controllers['x']._last_speed**2 +
        mgr.controllers['y']._last_speed**2 +
        (mgr.controllers['z']._last_speed or 0.0)**2
    ) ** 0.5
    assert total == pytest.approx(0.01)


def test_sub_100_nm_speed_not_clamped():
    app = QCoreApplication.instance() or QCoreApplication([])
    mgr = ManipulatorManager(motion_logging=False)
    mgr.controllers = {
        'x': DummyCtrl(0.0),
        'y': DummyCtrl(0.0),
        'z': DummyCtrl(0.0),
    }
    start = (0.0, 0.0, 0.0)
    target = (1.0, 0.0, 0.0)
    assert mgr._move_axes(start, target, MIN_AXIS_SPEED)
    assert mgr.controllers['x']._last_speed == pytest.approx(MIN_AXIS_SPEED)
    assert mgr.controllers['y']._last_speed is None
    assert mgr.controllers['z']._last_speed is None


def test_execute_path_logs_start_and_end():
    app = QCoreApplication.instance() or QCoreApplication([])
    mgr = ManipulatorManager(motion_logging=False)
    mgr.controllers = {
        'x': DummyCtrl(0.0),
        'y': DummyCtrl(0.0),
        'z': DummyCtrl(0.0),
    }
    done = threading.Event()
    mgr.pattern_completed.connect(lambda: done.set())

    mgr.execute_path([(1.0, 2.0, 3.0)], 0.1)

    for _ in range(50):
        if done.wait(0.1):
            break
        app.processEvents()

    assert done.is_set()
    log = mgr.get_modbus_log()
    start = [e for e in log if e["axis"] == "PATH" and e["action"] == "pattern_start"]
    end = [e for e in log if e["axis"] == "PATH" and e["action"] == "pattern_completed"]
    assert start and end
    assert "start=(0.0, 0.0, 0.0)" in start[-1]["description"]
    assert "end=(1.0, 2.0, 3.0)" in end[-1]["description"]
    assert end[-1]["time"] >= start[-1]["time"]


def test_stop_and_go_dwell_uses_measured_move_time(monkeypatch):
    app = QCoreApplication.instance() or QCoreApplication([])
    mgr = ManipulatorManager(motion_logging=False)
    mgr.controllers = {
        'x': DummyCtrl(0.0),
        'y': DummyCtrl(0.0),
        'z': DummyCtrl(0.0),
    }
    mgr.nozzle_diameter_mm = 1.0

    class FakeTime:
        def __init__(self):
            self.current = 0.0
            self.slept = []

        def time(self):
            return self.current

        def sleep(self, duration):
            self.slept.append(duration)
            self.current += duration

        def advance(self, amount):
            self.current += amount

    fake_time = FakeTime()
    monkeypatch.setattr("controllers.manipulator_manager.time.time", fake_time.time)
    monkeypatch.setattr("controllers.manipulator_manager.time.sleep", fake_time.sleep)

    actual_move_duration = 0.5
    call_count = 0

    def fake_move_axes(start, target, speed, force_direct=False):
        nonlocal call_count
        call_count += 1
        fake_time.advance(actual_move_duration)
        return True

    mgr._move_axes = fake_move_axes

    start = (0.0, 0.0, 0.0)
    target = (0.2, 0.0, 0.0)
    requested_speed = 0.1
    distance = 0.2

    assert mgr._move_axes_stop_and_go(start, target, requested_speed, distance)
    assert call_count == 1

    total_sleep = sum(fake_time.slept)
    expected_dwell = max(0.0, (distance / requested_speed) - actual_move_duration)
    assert total_sleep == pytest.approx(expected_dwell)
