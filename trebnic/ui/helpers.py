import flet as ft 
from datetime import date 
from typing import Optional 

from config import COLORS 


def format_duration(minutes: int) -> str: 
    if minutes < 60: 
        return f"{minutes} min" 
    h, m = divmod(minutes, 60) 
    if m == 0: 
        return f"{h} hr" if h == 1 else f"{h} hrs" 
    return f"{h} hr {m} min" if h == 1 else f"{h} hrs {m} min" 


def seconds_to_time(seconds: int) -> str: 
    minutes = seconds // 60 
    if minutes < 60: 
        return f"{minutes} min" 
    h, m = divmod(minutes, 60) 
    return f"{h}h" if m == 0 else f"{h}h {m}m" 


def format_timer_display(seconds: int) -> str: 
    return f"{seconds // 60:02d}:{seconds % 60:02d}" 


def format_due_date(due_date: Optional[date]) -> Optional[str]: 
    if due_date is None: 
        return None 
    delta = (due_date - date.today()).days 
    date_str = due_date.strftime("%b %d") 
    if delta < 0: 
        return f"🔴 {date_str}" 
    elif delta == 0: 
        return "📅 Today" 
    elif delta == 1: 
        return "📆 Tomorrow" 
    elif delta <= 7: 
        return f"🗓️ {date_str}" 
    return f"📋 {date_str}" 


def accent_btn(text: str, on_click) -> ft.ElevatedButton: 
    return ft.ElevatedButton(text, on_click=on_click, bgcolor=COLORS["accent"], color=COLORS["white"]) 


def danger_btn(text: str, on_click, icon=None) -> ft.ElevatedButton: 
    return ft.ElevatedButton(text, on_click=on_click, bgcolor=COLORS["danger"], color=COLORS["white"], icon=icon) 


class SnackService: 
    def __init__(self, page: ft.Page): 
        self.page = page 
        self.snack = ft.SnackBar(content=ft.Text(""), bgcolor=COLORS["card"], duration=2000) 
        page.overlay.append(self.snack) 

    def show(self, message: str, color=None, update=True): 
        self.snack.content = ft.Text(message, color=COLORS["white"]) 
        self.snack.bgcolor = color or COLORS["card"] 
        self.snack.open = True 
        if update: 
            self.page.update() 