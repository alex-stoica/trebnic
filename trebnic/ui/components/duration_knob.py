"""Duration picker with circular slider (mobile) or flat slider (desktop fallback).

Uses flet-circular-slider when available (Android APK build), falls back to
native ft.Slider on desktop where the Flutter extension isn't compiled in.
"""
import flet as ft
from typing import Callable, Optional

from config import (
    COLORS,
    FONT_SIZE_SM,
    FONT_SIZE_3XL,
    DURATION_KNOB_MIN_MINUTES,
    DURATION_KNOB_MAX_MINUTES,
)
from i18n import t

CIRCULAR_SLIDER_AVAILABLE = False
try:
    from flet_circular_slider import FletCircularSlider
    CIRCULAR_SLIDER_AVAILABLE = True
except ImportError:
    pass


class DurationKnob(ft.Container):
    """Duration picker for selecting time duration (5 min – 8h 20m).

    Uses a circular radial slider when flet-circular-slider is installed,
    otherwise falls back to a plain ft.Slider. Public API is identical
    regardless of backend.
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

        if CIRCULAR_SLIDER_AVAILABLE:
            layout = self._build_circular_layout()
        else:
            layout = self._build_slider_layout()

        super().__init__(content=layout, width=size)

    # -- public API (unchanged) ------------------------------------------------

    @property
    def value(self) -> int:
        """Get current duration in minutes."""
        return self._minutes

    @value.setter
    def value(self, minutes: int) -> None:
        """Set duration in minutes."""
        self._minutes = self._clamp(minutes)
        if CIRCULAR_SLIDER_AVAILABLE:
            self._circular.value = self._minutes
            self._circular.update()
        else:
            self._duration_text.value = self._format_duration(self._minutes)
            self._slider.value = self._minutes
            self._duration_text.update()
            self._slider.update()

    def set_on_change(self, callback: Optional[Callable[[int], None]]) -> None:
        """Set the callback for when the duration value changes."""
        self._on_change = callback

    # -- circular layout (primary) ---------------------------------------------

    def _build_circular_layout(self) -> ft.Column:
        divisions = (DURATION_KNOB_MAX_MINUTES - DURATION_KNOB_MIN_MINUTES) // 5

        self._circular = FletCircularSlider(
            min=DURATION_KNOB_MIN_MINUTES,
            max=DURATION_KNOB_MAX_MINUTES,
            value=self._minutes,
            divisions=divisions,
            size=self._size,
            label_formatter=self._format_duration_float,
            inner_text_color=COLORS["accent"],
            progress_bar_width=12,
            track_width=8,
            handler_size=16,
            progress_bar_start_color=COLORS["accent"],
            progress_bar_end_color=COLORS["accent"],
            track_color=COLORS["input_bg"],
            dot_color=COLORS["accent"],
            on_change=self._on_circular_change,
        )

        return ft.Column(
            [
                ft.Icon(ft.Icons.TIMER, size=24, color=COLORS["done_text"]),
                self._circular,
                ft.Text(t("drag_to_adjust"), size=FONT_SIZE_SM, color=COLORS["done_text"], text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        )

    def _on_circular_change(self, e: ft.ControlEvent) -> None:
        """Handle circular slider value change — snap to nearest 5 min.

        Text formatting is handled Dart-side via label_map for zero-latency updates.
        Python only tracks the snapped value.
        """
        try:
            raw = float(e.data)
            snapped = int(round(raw / 5.0) * 5)
            snapped = self._clamp(snapped)

            if snapped != self._minutes:
                self._minutes = snapped
                if self._on_change:
                    self._on_change(self._minutes)
        except (ValueError, TypeError) as exc:
            print(f"[DEBUG] circular slider error: {exc!r}")

    # -- flat slider layout (fallback) -----------------------------------------

    def _build_slider_layout(self) -> ft.Column:
        divisions = (DURATION_KNOB_MAX_MINUTES - DURATION_KNOB_MIN_MINUTES) // 5

        self._duration_text = ft.Text(
            self._format_duration(self._minutes),
            size=FONT_SIZE_3XL,
            weight=ft.FontWeight.BOLD,
            color=COLORS["accent"],
            text_align=ft.TextAlign.CENTER,
        )

        self._slider = ft.Slider(
            min=DURATION_KNOB_MIN_MINUTES,
            max=DURATION_KNOB_MAX_MINUTES,
            divisions=divisions,
            value=self._minutes,
            active_color=COLORS["accent"],
            thumb_color=COLORS["accent"],
            inactive_color=COLORS["input_bg"],
            on_change=self._on_slider_change,
        )

        return ft.Column(
            [
                ft.Icon(ft.Icons.TIMER, size=24, color=COLORS["done_text"]),
                self._duration_text,
                ft.Text(t("drag_to_adjust"), size=FONT_SIZE_SM, color=COLORS["done_text"], text_align=ft.TextAlign.CENTER),
                self._slider,
                ft.Row(
                    [
                        ft.Text("5m", size=FONT_SIZE_SM, color=COLORS["done_text"]),
                        ft.Container(expand=True),
                        ft.Text("8h20m", size=FONT_SIZE_SM, color=COLORS["done_text"]),
                    ],
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        )

    def _on_slider_change(self, e: ft.ControlEvent) -> None:
        """Handle flat slider value change."""
        try:
            raw = float(e.data) if e.data else e.control.value
            new_minutes = int(round(raw))
            new_minutes = self._clamp(new_minutes)

            if new_minutes != self._minutes:
                self._minutes = new_minutes
                self._duration_text.value = self._format_duration(self._minutes)
                self._duration_text.update()
                if self._on_change:
                    self._on_change(self._minutes)
        except (ValueError, TypeError) as exc:
            print(f"[DEBUG] slider error: {exc!r}")

    # -- shared helpers --------------------------------------------------------

    def _clamp(self, minutes: int) -> int:
        """Clamp minutes to valid range."""
        return max(DURATION_KNOB_MIN_MINUTES, min(DURATION_KNOB_MAX_MINUTES, minutes))

    def _format_duration_float(self, minutes: float) -> str:
        """Format minutes for label_formatter (accepts float from slider)."""
        return self._format_duration(int(minutes))

    def _format_duration(self, minutes: int) -> str:
        """Format minutes for display."""
        if minutes < 60:
            return f"{minutes}m"
        h, m = divmod(minutes, 60)
        return f"{h}h {m}m" if m > 0 else f"{h}h"
