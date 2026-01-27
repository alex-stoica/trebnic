"""Dialog utilities - factory functions for consistent dialog styling.

open_dialog() creates modal dialogs with standard layout (title, content, actions).
create_option_item() builds clickable rows used in selection dialogs and menus.
"""
import flet as ft
from typing import Callable, Tuple, Optional, List

from config import COLORS


def open_dialog(
    page: ft.Page, 
    title: str, 
    content: ft.Control, 
    make_actions: Callable[[Callable[[], None]], List[ft.Control]], 
) -> Tuple[ft.AlertDialog, Callable[[], None]]: 
    holder: List[Optional[ft.AlertDialog]] = [None] 

    def close(e: Optional[ft.ControlEvent] = None) -> None: 
        if holder[0]: 
            page.close(holder[0]) 

    holder[0] = ft.AlertDialog(
        modal=True, 
        title=ft.Text(title), 
        content=content, 
        actions=make_actions(close), 
        actions_alignment=ft.MainAxisAlignment.END, 
    ) 
    page.open(holder[0])
    return holder[0], close


def create_option_item(
    icon: str, 
    text: str, 
    on_click: Callable[[ft.ControlEvent], None], 
    color: str = COLORS["accent"], 
    text_color: Optional[str] = None, 
    as_popup: bool = False, 
) -> ft.Control: 
    row = ft.Row(
        [ 
            ft.Icon(icon, size=18, color=color), 
            ft.Text(text, size=14, color=text_color, expand=not as_popup), 
        ], 
        spacing=12, 
    ) 

    if as_popup:
        return ft.PopupMenuItem(
            content=ft.Container(
                content=row, 
                padding=ft.padding.symmetric(vertical=5, horizontal=10), 
            ), 
            on_click=on_click,
        ) 

    return ft.Container(
        content=row,
        padding=ft.padding.symmetric(vertical=10, horizontal=15),
        border_radius=8,
        ink=True,
        on_click=on_click,
    ) 