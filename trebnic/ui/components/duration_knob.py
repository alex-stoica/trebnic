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
    """Circular/radial slider for duration selection.
    
    Start time is fixed; this controls duration from 5 min to 8h 20m.
    Drag around the circle or tap to set duration.
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
        self._track_radius = (size - 50) / 2
        self._thumb_size = 28
        
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
                blur_radius=8,
                spread_radius=1,
                color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
            ),
        )
        
        self._position_thumb()
        
        track = ft.Container(
            width=size - 20,
            height=size - 20,
            border_radius=(size - 20) // 2,
            border=ft.border.all(8, COLORS["input_bg"]),
            left=10,
            top=10,
        )
        
        progress = self._get_progress()
        self._active_ring = ft.Container(
            width=size - 20,
            height=size - 20,
            border_radius=(size - 20) // 2,
            border=ft.border.all(8, COLORS["accent"]),
            left=10,
            top=10,
            opacity=0.3 + progress * 0.5,
        )
        
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
            width=size - 80,
            height=size - 80,
            border_radius=(size - 80) // 2,
            bgcolor=COLORS["card"],
            alignment=ft.alignment.center,
            left=40,
            top=40,
        )
        
        min_label = ft.Container(
            content=ft.Text("5m", size=FONT_SIZE_SM, color=COLORS["done_text"]),
            left=20,
            bottom=20,
        )
        max_label = ft.Container(
            content=ft.Text("8h20m", size=FONT_SIZE_SM, color=COLORS["done_text"]),
            right=10,
            bottom=20,
        )
        
        content_stack = ft.Stack(
            [track, self._active_ring, center, self._thumb, min_label, max_label],
            width=size,
            height=size,
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
    
    def _clamp(self, minutes: int) -> int:
        """Clamp minutes to valid range."""
        return max(DURATION_KNOB_MIN_MINUTES, min(DURATION_KNOB_MAX_MINUTES, minutes))
    
    def _get_progress(self) -> float:
        """Get progress from 0 to 1."""
        return (self._minutes - DURATION_KNOB_MIN_MINUTES) / (
            DURATION_KNOB_MAX_MINUTES - DURATION_KNOB_MIN_MINUTES
        )
    
    def _minutes_to_angle(self, minutes: int) -> float:
        """Convert minutes to angle. Arc: 225° to -45° (270° sweep clockwise)."""
        progress = (minutes - DURATION_KNOB_MIN_MINUTES) / (
            DURATION_KNOB_MAX_MINUTES - DURATION_KNOB_MIN_MINUTES
        )
        start = math.radians(225)
        sweep = math.radians(270)
        return start - progress * sweep
    
    def _angle_to_minutes(self, angle: float) -> int:
        """Convert angle to minutes with 5-minute snap."""
        start = math.radians(225)
        sweep = math.radians(270)
        
        diff = start - angle
        if diff < 0:
            diff += 2 * math.pi
        if diff > sweep:
            diff = sweep if diff < sweep + math.pi else 0
        
        progress = min(1.0, max(0.0, diff / sweep))
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
        dy = self._center - local_y
        angle = math.atan2(dy, dx)
        new_minutes = self._angle_to_minutes(angle)
        
        if new_minutes != self._minutes:
            self._minutes = new_minutes
            self._update_display()
            if self._on_change:
                self._on_change(self._minutes)
    
    def _update_display(self) -> None:
        """Update visual elements."""
        self._position_thumb()
        self._duration_text.value = self._format_duration(self._minutes)
        self._active_ring.opacity = 0.3 + self._get_progress() * 0.5
        self.update()