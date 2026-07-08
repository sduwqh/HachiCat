"""Pet behavior state machine.

References:
- DyberPet: event-driven state pipeline (trigger → buffModule → statusUI)
- KillClawd: simple enum state machine with randomized durations in tick()
- OpenPet: 6 companion events mapped to specific animations

Design:
- Flat enum with clear transitions
- Autonomy timers for idle → walk → sleep progression
- States map 1:1 to animation names in FrameAnimator
"""

import random
from enum import Enum, auto

from PySide6.QtCore import QObject, QTimer, Signal


class PetState(Enum):
    """All possible pet behavioral states."""
    IDLE = auto()       # Standing/sitting, idle animation
    WALKING = auto()    # Moving across screen
    SLEEPING = auto()   # Inactive after timeout
    DRAGGING = auto()   # Being dragged by user
    WORKING = auto()    # Agent is executing a task
    HAPPY = auto()      # Task succeeded — celebration
    SAD = auto()        # Task failed — disappointment


# Map state to animation name (matches sprite_config.json)
STATE_ANIMATION: dict[PetState, str] = {
    PetState.IDLE: "idle",
    PetState.WALKING: "walk",
    PetState.SLEEPING: "sleep",
    PetState.DRAGGING: "drag",
    PetState.WORKING: "working",
    PetState.HAPPY: "happy",
    PetState.SAD: "sad",
}


class PetStateMachine(QObject):
    """Manages pet state transitions and autonomous behaviors.

    Signals notify the PetWindow to update animations and movement.
    """

    state_changed = Signal(PetState, PetState)  # (old_state, new_state)
    walk_target_changed = Signal(int, int)       # (target_x, target_y)

    def __init__(
        self,
        idle_timeout_ms: int = 5000,       # Idle before starting to walk
        walk_interval_ms: int = 8000,       # How often to pick new walk target
        sleep_timeout_ms: int = 300_000,    # Inactivity before sleep (5 min)
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._state = PetState.IDLE
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)

        self._walk_timer = QTimer(self)
        self._walk_timer.timeout.connect(self._pick_walk_target)
        self._walk_interval = walk_interval_ms

        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.timeout.connect(self._on_sleep_timeout)
        self._sleep_timeout = sleep_timeout_ms

        self._idle_timeout = idle_timeout_ms
        self._last_activity: float = 0.0

        # Start in IDLE
        self._enter_idle()

    @property
    def state(self) -> PetState:
        return self._state

    @property
    def animation_name(self) -> str:
        return STATE_ANIMATION.get(self._state, "idle")

    # --- Public API ---

    def on_user_interaction(self) -> None:
        """Called on any user interaction (click, drag, hotkey).
        Wakes pet from sleep, resets idle timers.
        """
        self._reset_activity()
        if self._state == PetState.SLEEPING:
            self._transition_to(PetState.IDLE)

    def on_drag_start(self) -> None:
        """Called when user starts dragging the pet."""
        self._reset_activity()
        self._transition_to(PetState.DRAGGING)

    def on_drag_end(self) -> None:
        """Called when user releases the pet after dragging."""
        self._transition_to(PetState.IDLE)

    def on_task_start(self) -> None:
        """Called when agent begins executing a task."""
        self._transition_to(PetState.WORKING)

    def on_task_done(self, success: bool = True) -> None:
        """Called when agent finishes a task. Plays happy/sad then returns to idle."""
        target = PetState.HAPPY if success else PetState.SAD
        self._transition_to(target)
        # Auto-return to IDLE after reaction animation plays
        QTimer.singleShot(2000, lambda: self._maybe_transition_to(PetState.IDLE))

    def set_autonomy_enabled(self, enabled: bool) -> None:
        """Enable/disable autonomous walking and sleeping."""
        self._autonomy_enabled = enabled
        if enabled:
            if self._state == PetState.IDLE:
                self._idle_timer.start(self._idle_timeout)
                self._sleep_timer.start(self._sleep_timeout)
        else:
            self._idle_timer.stop()
            self._walk_timer.stop()
            self._sleep_timer.stop()
            if self._state in (PetState.WALKING, PetState.IDLE):
                self._transition_to(PetState.IDLE)

    # --- Internal transitions ---

    def _transition_to(self, new_state: PetState) -> None:
        """Transition to a new state. Emits signal, manages timers."""
        if new_state == self._state:
            return

        old_state = self._state
        self._state = new_state

        # Stop all autonomy timers
        self._idle_timer.stop()
        self._walk_timer.stop()
        self._sleep_timer.stop()

        # Enter behavior for new state
        if new_state == PetState.IDLE:
            self._enter_idle()
        elif new_state == PetState.WALKING:
            self._enter_walking()
        elif new_state == PetState.SLEEPING:
            self._enter_sleeping()

        self.state_changed.emit(old_state, new_state)

    def _maybe_transition_to(self, new_state: PetState) -> None:
        """Transition only if still in the expected temporary state."""
        if self._state in (PetState.HAPPY, PetState.SAD, PetState.WORKING):
            self._transition_to(new_state)

    def _enter_idle(self) -> None:
        """Enter IDLE: start autonomy timers only if enabled."""
        if getattr(self, '_autonomy_enabled', False):
            self._idle_timer.start(self._idle_timeout)
            self._sleep_timer.start(self._sleep_timeout)

    def _enter_walking(self) -> None:
        """Enter WALKING: only if autonomy is enabled."""
        if not getattr(self, '_autonomy_enabled', False):
            self._transition_to(PetState.IDLE)
            return
        self._walk_timer.start(self._walk_interval)
        self._pick_walk_target()
        self._sleep_timer.start(self._sleep_timeout)

    def _enter_sleeping(self) -> None:
        """Enter SLEEPING: all timers stopped, waiting for user interaction."""
        pass

    def _on_idle_timeout(self) -> None:
        """Idle for too long → start walking."""
        if self._state == PetState.IDLE:
            self._transition_to(PetState.WALKING)

    def _on_sleep_timeout(self) -> None:
        """No activity for very long → go to sleep."""
        if self._state in (PetState.IDLE, PetState.WALKING):
            self._transition_to(PetState.SLEEPING)

    def _pick_walk_target(self) -> None:
        """Pick a random position on screen and emit signal."""
        import random as rnd
        # Target will be clamped by PetWindow
        tx = rnd.randint(100, 1800)
        ty = rnd.randint(100, 900)
        self.walk_target_changed.emit(tx, ty)

    def _reset_activity(self) -> None:
        """Reset sleep timer on user interaction."""
        if self._state != PetState.SLEEPING:
            self._sleep_timer.start(self._sleep_timeout)
