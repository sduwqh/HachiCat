"""Frame animation engine for sprite sheets.

References:
- DyberPet: act_conf.json — per-action frame sequences with frame_refresh timing
- OpenPet: animation.ts — spritesheet atlas with per-frame durations, getPetFrameAtTime()
- KillClawd: simple state-to-GIF mapping with cooldown logic

Design:
- Each animation state maps to a row in the sprite sheet
- sprite_config.json defines: cell_width, cell_height, rows, columns, states
- QTimer drives frame advancement at configurable intervals
- Supports loop (cycle back to frame 0) and oneshot (hold last frame) modes
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass
class AnimationState:
    """Definition of one animation state."""
    name: str                        # "idle", "walk", "sleep", etc.
    row: int                         # Row index in sprite sheet
    frame_count: int                 # Number of frames in this row
    frame_durations: list[int]       # Duration per frame in milliseconds
    loop: bool = True                # True = cycle, False = play once
    next_state: str | None = None    # Transition to this state when done (oneshot only)


@dataclass
class SpriteConfig:
    """Sprite sheet metadata, loaded from sprite_config.json."""
    cell_width: int = 128
    cell_height: int = 128
    columns: int = 4
    rows: int = 8
    default_state: str = "idle"
    states: list[AnimationState] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpriteConfig":
        states = [
            AnimationState(
                name=s["name"],
                row=s["row"],
                frame_count=s["frame_count"],
                frame_durations=s.get("frame_durations", [150] * s["frame_count"]),
                loop=s.get("loop", True),
                next_state=s.get("next_state"),
            )
            for s in data.get("states", [])
        ]
        return cls(
            cell_width=data.get("cell_width", 128),
            cell_height=data.get("cell_height", 128),
            columns=data.get("columns", 4),
            rows=data.get("rows", 8),
            default_state=data.get("default_state", "idle"),
            states=states,
        )


class FrameAnimator(QObject):
    """Drives sprite-sheet frame animation via QTimer.

    Emits frame_changed(col, row) signals; the PetWidget listens
    and updates the displayed sub-rect of the sprite sheet.
    """

    frame_changed = Signal(int, int)  # (column, row) of current frame
    state_changed = Signal(str)       # new state name

    def __init__(self, config: SpriteConfig, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config
        self._states: dict[str, AnimationState] = {
            s.name: s for s in config.states
        }
        self._current_state: AnimationState | None = None
        self._current_frame_index: int = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_frame)

    @property
    def current_state_name(self) -> str:
        return self._current_state.name if self._current_state else ""

    @property
    def current_frame_col(self) -> int:
        return self._current_frame_index

    @property
    def current_frame_row(self) -> int:
        return self._current_state.row if self._current_state else 0

    def play(self, state_name: str) -> None:
        """Switch to and start playing an animation state."""
        state = self._states.get(state_name)
        if state is None:
            return

        # Only restart if different state
        if self._current_state is not state:
            self._current_state = state
            self._current_frame_index = 0
            self.state_changed.emit(state_name)
            self._emit_current_frame()

        self._timer.stop()
        if state.frame_count > 0:
            duration = state.frame_durations[0] if state.frame_durations else 180
            self._timer.start(duration)

    def _advance_frame(self) -> None:
        """Move to next frame; loop or hold based on state config."""
        if self._current_state is None:
            return

        self._current_frame_index += 1

        if self._current_frame_index >= self._current_state.frame_count:
            if self._current_state.loop:
                self._current_frame_index = 0
            else:
                # Oneshot — hold last frame
                self._current_frame_index = self._current_state.frame_count - 1
                self._timer.stop()
                # Transition if configured
                if self._current_state.next_state:
                    self.play(self._current_state.next_state)
                    return

        self._emit_current_frame()

        # Adjust timer interval for next frame
        durations = self._current_state.frame_durations
        if self._timer.isActive() and durations:
            idx = self._current_frame_index % len(durations)
            self._timer.setInterval(durations[idx])

    def _emit_current_frame(self) -> None:
        """Emit the current frame position."""
        if self._current_state:
            self.frame_changed.emit(
                self._current_frame_index,
                self._current_state.row,
            )

    def stop(self) -> None:
        """Stop the animation timer."""
        self._timer.stop()

    def resume(self) -> None:
        """Resume after being stopped."""
        if (self._current_state and self._current_state.frame_count > 1
                and self._current_state.frame_durations):
            idx = self._current_frame_index % len(self._current_state.frame_durations)
            self._timer.start(self._current_state.frame_durations[idx])

    @classmethod
    def from_config_path(cls, config_path: Path, parent: QObject | None = None) -> "FrameAnimator":
        """Factory: load sprite config from JSON file."""
        data = json.loads(config_path.read_text(encoding="utf-8"))
        config = SpriteConfig.from_dict(data)
        return cls(config, parent)
