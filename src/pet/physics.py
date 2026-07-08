"""Pet physics engine — drag, throw, and movement.

References:
- KillClawd: simple Euler integration with friction (0.92) and edge bounce (0.6).
  No complex physics library — hand-rolled in ~20 lines.
  Velocity tracking during drag, momentum on release.
- DyberPet: optional gravity + bounce + inertia with boundary clamping.

Design:
- Pet movement driven by velocity (vx, vy) per tick
- Drag: record position deltas → compute velocity on release
- Throw: apply velocity * multiplier on release, decay with friction
- Walk: set target position, move toward it at fixed speed
- Edge clamping keeps pet on screen
"""

import math
import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, QTimer, QObject


@dataclass
class PhysicsConfig:
    """Tunable physics parameters."""
    friction: float = 0.92           # Velocity multiplier per tick (0-1)
    bounce_coefficient: float = 0.6  # Energy retained on edge bounce (0-1)
    throw_multiplier: float = 3.5    # Drag velocity amplified on throw
    min_throw_speed: float = 3.0     # Below this, no throw (just drop)
    walk_speed: float = 1.8          # Pixels per tick when walking
    stop_threshold: float = 0.8      # Speed below which pet stops
    gravity: float = 0.0             # Downward acceleration (0 = no gravity)
    tick_interval_ms: int = 16       # ~60 fps


class PetPhysics(QObject):
    """Drives pet movement: walking toward targets and throw physics.

    Uses a QTimer at ~60fps for the physics tick.
    Reports position changes via callback.
    """

    def __init__(
        self,
        config: PhysicsConfig | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.config = config or PhysicsConfig()

        # Current state
        self._x: float = 0.0
        self._y: float = 0.0
        self._vx: float = 0.0
        self._vy: float = 0.0

        # Walk target
        self._target_x: float | None = None
        self._target_y: float | None = None

        # Drag velocity tracking (KillClawd pattern)
        self._drag_prev_x: float = 0.0
        self._drag_prev_y: float = 0.0
        self._drag_vx: float = 0.0
        self._drag_vy: float = 0.0

        # Modes
        self._is_dragging: bool = False
        self._is_throwing: bool = False
        self._is_walking: bool = False

        # Screen bounds (updated externally)
        self._screen_width: int = 1920
        self._screen_height: int = 1080
        self._pet_width: int = 128
        self._pet_height: int = 128

        # Tick timer
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.setInterval(self.config.tick_interval_ms)

        # Position update callback: (new_x, new_y) -> None
        self.on_position_changed: Callable[[int, int], None] | None = None

    # --- Public API ---

    def set_position(self, x: int, y: int) -> None:
        """Set absolute position (used on startup and during drag)."""
        self._x = float(x)
        self._y = float(y)

    def set_screen_bounds(self, screen_w: int, screen_h: int,
                          pet_w: int = 0, pet_h: int = 0) -> None:
        """Update screen dimensions for boundary clamping."""
        self._screen_width = screen_w
        self._screen_height = screen_h
        self._pet_width = pet_w or self._pet_width
        self._pet_height = pet_h or self._pet_height

    def start(self) -> None:
        """Begin the physics tick loop."""
        self._tick_timer.start()

    def stop(self) -> None:
        """Stop the physics tick loop."""
        self._tick_timer.stop()

    # --- Drag & Throw (KillClawd pattern) ---

    def drag_start(self, screen_x: int, screen_y: int) -> None:
        """Begin drag — start tracking velocity."""
        self._is_dragging = True
        self._is_throwing = False
        self._is_walking = False
        self._drag_prev_x = float(screen_x)
        self._drag_prev_y = float(screen_y)
        self._vx = 0.0
        self._vy = 0.0

    def drag_move(self, screen_x: int, screen_y: int) -> None:
        """Move pet during drag, tracking velocity."""
        if not self._is_dragging:
            return

        # Track velocity from last position delta
        self._drag_vx = screen_x - self._drag_prev_x
        self._drag_vy = screen_y - self._drag_prev_y

        self._drag_prev_x = float(screen_x)
        self._drag_prev_y = float(screen_y)

        self._x = float(screen_x)
        self._y = float(screen_y)

    def drag_end(self) -> bool:
        """End drag. Returns True if it was a throw (speed > threshold)."""
        self._is_dragging = False

        speed = math.hypot(self._drag_vx, self._drag_vy)

        if speed > self.config.min_throw_speed:
            self._is_throwing = True
            self._vx = self._drag_vx * self.config.throw_multiplier
            self._vy = self._drag_vy * self.config.throw_multiplier
            return True

        # Not a throw — just drop in place
        self._vx = 0.0
        self._vy = 0.0
        return False

    # --- Walk ---

    def walk_to(self, target_x: int, target_y: int) -> None:
        """Set a walk target. Pet moves toward it each tick."""
        self._target_x = float(target_x)
        self._target_y = float(target_y)
        self._is_walking = True
        self._is_throwing = False

    def stop_walking(self) -> None:
        """Cancel walk movement."""
        self._is_walking = False
        self._target_x = None
        self._target_y = None
        self._vx = 0.0
        self._vy = 0.0

    # --- Physics Tick ---

    def _tick(self) -> None:
        """One physics step (~16ms)."""
        if self._is_dragging:
            self._emit_position()
            return

        # --- Throw physics ---
        if self._is_throwing:
            # Apply friction
            self._vx *= self.config.friction
            self._vy *= self.config.friction

            # Apply gravity
            self._vy += self.config.gravity

            # Move
            self._x += self._vx
            self._y += self._vy

            # Bounce off edges (KillClawd pattern)
            bounced = False
            min_x = 0.0
            max_x = float(self._screen_width - self._pet_width)
            min_y = 0.0
            max_y = float(self._screen_height - self._pet_height)

            if self._x <= min_x:
                self._x = min_x
                self._vx *= -self.config.bounce_coefficient
                bounced = True
            elif self._x >= max_x:
                self._x = max_x
                self._vx *= -self.config.bounce_coefficient
                bounced = True

            if self._y <= min_y:
                self._y = min_y
                self._vy *= -self.config.bounce_coefficient
                bounced = True
            elif self._y >= max_y:
                self._y = max_y
                self._vy *= -self.config.bounce_coefficient
                bounced = True

            # Stop when nearly still
            if math.hypot(self._vx, self._vy) < self.config.stop_threshold:
                self._is_throwing = False
                self._vx = 0.0
                self._vy = 0.0

            self._emit_position()
            return

        # --- Walk movement ---
        if self._is_walking and self._target_x is not None:
            dx = self._target_x - self._x
            dy = self._target_y - self._y
            dist = math.hypot(dx, dy)

            if dist < self.config.walk_speed * 2:
                # Arrived
                self._x = self._target_x
                self._y = self._target_y
                self._is_walking = False
                self._target_x = None
                self._target_y = None
                self._vx = 0.0
                self._vy = 0.0
            else:
                nx = dx / dist
                ny = dy / dist
                self._vx = nx * self.config.walk_speed
                self._vy = ny * self.config.walk_speed
                self._x += self._vx
                self._y += self._vy

            self._clamp_to_screen()
            self._emit_position()
            return

        # --- Idle (velocity decay) ---
        if abs(self._vx) > 0.01 or abs(self._vy) > 0.01:
            self._vx *= self.config.friction
            self._vy *= self.config.friction
            self._x += self._vx
            self._y += self._vy
            self._clamp_to_screen()
            self._emit_position()

    def _clamp_to_screen(self) -> None:
        """Keep pet within visible screen bounds."""
        min_x = 0.0
        max_x = float(self._screen_width - self._pet_width)
        min_y = 0.0
        max_y = float(self._screen_height - self._pet_height)

        self._x = max(min_x, min(self._x, max_x))
        self._y = max(min_y, min(self._y, max_y))

    def _emit_position(self) -> None:
        """Notify listener of new position."""
        if self.on_position_changed:
            self.on_position_changed(int(self._x), int(self._y))

    @property
    def is_throwing(self) -> bool:
        return self._is_throwing

    @property
    def is_walking(self) -> bool:
        return self._is_walking

    @property
    def position(self) -> tuple[int, int]:
        return int(self._x), int(self._y)
