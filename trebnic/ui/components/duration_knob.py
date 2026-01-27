"""Radial duration picker - horseshoe-shaped knob for selecting time duration.

Used in task completion dialog when no timer was running. Drag around the arc
or tap to set duration (5 min to 8h 20m). Heavy on gesture math and canvas drawing.
"""
import flet as ft
import math
from typing import Callable, Optional

from config import (
    COLORS,
    FONT_SIZE_SM,
    FONT_SIZE_3XL,
    DURATION_KNOB_MIN_MINUTES,
    DURATION_KNOB_MAX_MINUTES,
)


class DurationKnob(ft.Container):
    """Horseshoe-shaped radial slider for duration selection.

    Start time is fixed; this controls duration from 5 min to 8h 20m.
    Drag around the arc or tap to set duration.
    """

    def __init__(
        self,
        initial_minutes: int = 30,
        on_change: Optional[Callable[[int], None]] = None,
        size: int = 200,
    ) -> None:
        self._minutes = self._clamp(initial_minutes)
        self._on_change = on_change
        self._size = size
        self._center = size / 2
        self._track_radius = (size - 36) / 2  # Pushed outward
        self._thumb_size = 30
        self._track_width = 12  # Fatter track

        # Arc angles: horseshoe from 220° to -40° (260° sweep)
        self._start_angle = 220  # degrees
        self._end_angle = -40    # degrees (320° in positive)
        self._sweep = 260        # degrees

        self._duration_text: ft.Text = ft.Text(
            self._format_duration(self._minutes),
            size=FONT_SIZE_3XL,
            weight="bold",
            color=COLORS["accent"],
        )

        self._thumb: ft.Container = ft.Container(
            width=self._thumb_size,
            height=self._thumb_size,
            border_radius=self._thumb_size // 2,
            bgcolor=COLORS["accent"],
            border=ft.border.all(4, COLORS["white"]),
            shadow=ft.BoxShadow(
                blur_radius=10,
                spread_radius=2,
                color=ft.Colors.with_opacity(0.4, ft.Colors.BLACK),
            ),
        )

        self._position_thumb()

        # Track ring (full circle, will be partially hidden)
        track_size = size - 16
        track = ft.Container(
            width=track_size,
            height=track_size,
            border_radius=track_size // 2,
            border=ft.border.all(self._track_width, COLORS["input_bg"]),
            left=(size - track_size) / 2,
            top=(size - track_size) / 2,
        )

        # Progress ring overlay
        self._progress_ring = ft.Container(
            width=track_size,
            height=track_size,
            border_radius=track_size // 2,
            border=ft.border.all(self._track_width, COLORS["accent"]),
            left=(size - track_size) / 2,
            top=(size - track_size) / 2,
            opacity=0.8,
        )

        # Bottom cover to create horseshoe effect
        cover_height = 50
        bottom_cover = ft.Container(
            width=size,
            height=cover_height,
            bgcolor=COLORS["bg"],
            left=0,
            top=size - cover_height + 5,
        )

        # Center display
        center_size = size - 80
        center = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.TIMER_OUTLINED, size=24, color=COLORS["done_text"]),
                    self._duration_text,
                    ft.Text("drag to adjust", size=FONT_SIZE_SM, color=COLORS["done_text"]),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                tight=True,
            ),
            width=center_size,
            height=center_size,
            border_radius=center_size // 2,
            bgcolor=COLORS["card"],
            alignment=ft.alignment.center,
            left=(size - center_size) / 2,
            top=(size - center_size) / 2,
        )

        min_label = ft.Container(
            content=ft.Text("5m", size=FONT_SIZE_SM, color=COLORS["done_text"]),
            left=12,
            bottom=8,
        )
        max_label = ft.Container(
            content=ft.Text("8h20m", size=FONT_SIZE_SM, color=COLORS["done_text"]),
            right=0,
            bottom=8,
        )

        content_stack = ft.Stack(
            [track, self._progress_ring, bottom_cover, center, self._thumb, min_label, max_label],
            width=size,
            height=size,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        gesture = ft.GestureDetector(
            content=content_stack,
            on_pan_update=self._on_drag,
            on_tap_down=self._on_tap,
        )

        super().__init__(content=gesture, width=size, height=size)

    @property
    def value(self) -> int:
        """Get current duration in minutes."""
        return self._minutes

    @value.setter
    def value(self, minutes: int) -> None:
        """Set duration in minutes."""
        self._minutes = self._clamp(minutes)
        self._update_display()

    def set_on_change(self, callback: Optional[Callable[[int], None]]) -> None:
        """Set the callback for when the duration value changes."""
        self._on_change = callback

    def _clamp(self, minutes: int) -> int:
        """Clamp minutes to valid range."""
        return max(DURATION_KNOB_MIN_MINUTES, min(DURATION_KNOB_MAX_MINUTES, minutes))

    def _get_progress(self) -> float:
        """Get progress from 0 to 1."""
        return (self._minutes - DURATION_KNOB_MIN_MINUTES) / (
            DURATION_KNOB_MAX_MINUTES - DURATION_KNOB_MIN_MINUTES
        )

    def _minutes_to_angle(self, minutes: int) -> float:
        """Convert minutes to angle in radians."""
        progress = (minutes - DURATION_KNOB_MIN_MINUTES) / (
            DURATION_KNOB_MAX_MINUTES - DURATION_KNOB_MIN_MINUTES
        )
        # Start at 220°, sweep clockwise (negative direction) by progress * 260°
        angle_deg = self._start_angle - progress * self._sweep
        return math.radians(angle_deg)

    def _angle_to_minutes(self, angle_rad: float) -> int:
        """Convert angle (radians) to minutes with 5-minute snap."""
        angle_deg = math.degrees(angle_rad)

        # Normalize angle to 0-360 range
        while angle_deg < 0:
            angle_deg += 360
        while angle_deg >= 360:
            angle_deg -= 360

        # The arc goes from 220° clockwise to 320° (through 0°)
        # Valid range: 220° -> 180° -> 90° -> 0° -> 320°

        # Check if angle is in the "dead zone" (320° to 220° going counterclockwise through top)
        # Dead zone is 320° < angle < 220° when going the short way (i.e., 320 to 360 to 0 to 220)
        # Actually: angles from 220° to 320° going counterclockwise (the short arc at bottom) are dead

        if angle_deg > 220 and angle_deg <= 320:
            # In the dead zone at the bottom - snap to nearest end
            if angle_deg < 270:
                return DURATION_KNOB_MIN_MINUTES  # Snap to start (220°)
            else:
                return DURATION_KNOB_MAX_MINUTES  # Snap to end (320°)

        # Calculate progress
        if angle_deg <= 220:
            # From 0° to 220°
            diff = 220 - angle_deg
        else:
            # From 320° to 360° (wraps around)
            diff = 220 + (360 - angle_deg)

        progress = diff / self._sweep
        progress = min(1.0, max(0.0, progress))

        raw = DURATION_KNOB_MIN_MINUTES + progress * (
            DURATION_KNOB_MAX_MINUTES - DURATION_KNOB_MIN_MINUTES
        )
        return int(round(raw / 5) * 5)

    def _get_thumb_position(self) -> tuple:
        """Get thumb center x, y based on current value."""
        angle = self._minutes_to_angle(self._minutes)
        x = self._center + self._track_radius * math.cos(angle)
        y = self._center - self._track_radius * math.sin(angle)
        return x, y

    def _position_thumb(self) -> None:
        """Set thumb position based on current minutes."""
        x, y = self._get_thumb_position()
        self._thumb.left = x - self._thumb_size / 2
        self._thumb.top = y - self._thumb_size / 2

    def _format_duration(self, minutes: int) -> str:
        """Format minutes for display."""
        if minutes < 60:
            return f"{minutes}m"
        h, m = divmod(minutes, 60)
        return f"{h}h {m}m" if m > 0 else f"{h}h"

    def _on_drag(self, e: ft.DragUpdateEvent) -> None:
        """Handle drag to update value."""
        self._update_from_position(e.local_x, e.local_y)

    def _on_tap(self, e: ft.TapEvent) -> None:
        """Handle tap to jump to position."""
        self._update_from_position(e.local_x, e.local_y)

    def _update_from_position(self, local_x: float, local_y: float) -> None:
        """Update minutes from screen position."""
        dx = local_x - self._center
        dy = self._center - local_y  # Flip y for standard math coords
        angle = math.atan2(dy, dx)
        new_minutes = self._angle_to_minutes(angle)
        new_minutes = self._clamp(new_minutes)

        if new_minutes != self._minutes:
            self._minutes = new_minutes
            self._update_display()
            if self._on_change:
                self._on_change(self._minutes)

    def _update_display(self) -> None:
        """Update visual elements."""
        self._position_thumb()
        self._duration_text.value = self._format_duration(self._minutes)
        # Update progress ring opacity based on progress
        self._progress_ring.opacity = 0.3 + self._get_progress() * 0.6
        self.update()
