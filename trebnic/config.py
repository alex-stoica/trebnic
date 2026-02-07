"""Application configuration - single source of truth for all constants.

Contains colors, dimensions, enums (NavItem, PageType, RecurrenceFrequency), and magic values.
Import from here instead of hardcoding values elsewhere to ensure consistency across the app.
"""
import os
from enum import Enum
from pathlib import Path

# Load .env if available (desktop only - not bundled in mobile builds)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # dotenv not available on mobile, skip loading .env


class RecurrenceFrequency(Enum):
    """Enum for task recurrence frequency types."""
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class NotificationType(Enum):
    """Enum for notification types."""
    TIMER_COMPLETE = "timer_complete"
    DUE_REMINDER = "due_reminder"
    OVERDUE = "overdue"
    DAILY_DIGEST = "daily_digest"


class PermissionResult(Enum):
    """Result of notification permission request."""
    GRANTED = "granted"
    DENIED = "denied"
    NOT_REQUIRED = "not_required"  # Desktop platforms don't need runtime permission 


class NavItem(Enum): 
    """Enum for navigation items."""
    INBOX = "inbox"
    TODAY = "today"
    CALENDAR = "calendar"
    UPCOMING = "upcoming"
    PROJECTS = "projects"


class PageType(Enum):
    """Enum for page types."""
    TASKS = "tasks"
    PROFILE = "profile"
    TIME_ENTRIES = "time_entries"
    HELP = "help"
    FEEDBACK = "feedback"
    STATS = "stats"

PROJECT_ICONS = [ 
    "📁", "🏃", "💼", "🧹", "📚", "🎮", "🎨", "🏠", "💡", "🎯",
    "🚀", "⭐", "🔥", "💎", "🌟", "🎵", "📱", "💻", "🎬", "📷",
    "✈️", "🏋️", "🍕", "☕", "🛒", "💰", "📊", "🔧", "📝", "🎓",
    "🔔", "👥", "💊", "🌱", "🔒", "⏳", "💬", "⚡", "📍", "📋",
    "🏆", "📅", "🤝", "📈", "🧘", "🌍", "🧪", "🔑", "🛠️", "📣",
    "🏥", "📞", "🎁", "🧳", "📦", "🎭", "🧠", "🛡️", "🎸", "📡",
]

PROJECT_COLORS = [
    {"name": "Blue", "value": "#2196f3"},
    {"name": "Green", "value": "#4caf50"},
    {"name": "Orange", "value": "#ff9800"},
    {"name": "Purple", "value": "#9c27b0"},
    {"name": "Red", "value": "#f44336"},
    {"name": "Teal", "value": "#009688"},
    {"name": "Pink", "value": "#e91e63"},
    {"name": "Indigo", "value": "#3f51b5"},
    {"name": "Amber", "value": "#ffc107"},
    {"name": "Cyan", "value": "#00bcd4"},
    {"name": "Deep Orange", "value": "#ff5722"},
    {"name": "Forest", "value": "#2e7d32"},
    {"name": "Brown", "value": "#795548"},
    {"name": "Grey", "value": "#9e9e9e"},
    {"name": "Lime", "value": "#8bc34a"},
    {"name": "Yellow", "value": "#eefa47"},
    {"name": "Maroon", "value": "#672A0E"},
]
 
BORDER_RADIUS = 10
BORDER_RADIUS_SM = 5 
BORDER_RADIUS_MD = 8 
BORDER_RADIUS_LG = 20 

MOBILE_BREAKPOINT = 768
ANIMATION_DELAY = 0.35
DATE_PICKER_YEARS = 2
 
DEFAULT_ESTIMATED_SECONDS = 900
DURATION_SLIDER_STEP = 5
DURATION_SLIDER_MIN = 1
DURATION_SLIDER_MAX = 100
DURATION_KNOB_MIN_MINUTES = 5  
DURATION_KNOB_MAX_MINUTES = 500  
SNACK_DURATION_MS = 2000 
 
DIALOG_WIDTH_SM = 280
DIALOG_WIDTH_MD = 300
DIALOG_WIDTH_LG = 320
DIALOG_WIDTH_XL = 350

CALENDAR_HEADER_HEIGHT = 48
ICON_PICKER_HEIGHT = 280
NOTES_FIELD_HEIGHT = 280
COLOR_PICKER_HEIGHT = 250 
 
ICON_GRID_RUNS_COUNT = 6 
ICON_GRID_MAX_EXTENT = 45 
ICON_GRID_SPACING = 5 
 
FONT_SIZE_XS = 9 
FONT_SIZE_SM = 10 
FONT_SIZE_MD = 12 
FONT_SIZE_BASE = 13 
FONT_SIZE_LG = 14 
FONT_SIZE_XL = 16 
FONT_SIZE_2XL = 18 
FONT_SIZE_3XL = 20 
FONT_SIZE_4XL = 24 
FONT_SIZE_5XL = 32 
 
ICON_SIZE_XS = 14 
ICON_SIZE_SM = 16 
ICON_SIZE_MD = 18 
ICON_SIZE_LG = 20 
ICON_SIZE_XL = 24 
ICON_SIZE_2XL = 48 
ICON_SIZE_3XL = 64 
 
SPACING_XS = 2 
SPACING_SM = 4 
SPACING_MD = 8 
SPACING_LG = 10 
SPACING_XL = 12 
SPACING_2XL = 15 
SPACING_3XL = 20 

PADDING_XS = 2
PADDING_SM = 4
PADDING_MD = 8
PADDING_LG = 10
PADDING_XL = 12
PADDING_2XL = 15
PADDING_3XL = 20
PADDING_4XL = 40

OPACITY_DONE = 0.6

SIDEBAR_WIDTH = 250
SIDEBAR_ITEM_PADDING_LEFT = 50
PROJECT_NAME_MAX_LENGTH = 50

GAP_THRESHOLD_SECONDS = 60
TIME_ENTRY_ROW_HEIGHT = 60
MIN_TIMER_SECONDS = 300  # Minimum time entry is 5 minutes   
 
# Resend email API for feedback (free: 100 emails/day)
# Get your API key at https://resend.com/api-keys
# Fallback values for mobile (env vars not available)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "") or "re_HnHAZnqJ_2UmbtCVJDF8ChFmTfj8WTJU3"
FEEDBACK_EMAIL = os.getenv("FEEDBACK_EMAIL", "") or "alexstoica@protonmail.com"

# ============================================================================
# Encryption & Authentication
# ============================================================================

# Fields that should be encrypted when encryption is enabled
# Format: (table_name, column_name)
ENCRYPTED_FIELDS = [
    ("tasks", "title"),
    ("tasks", "notes"),
    ("projects", "name"), 
]

# Minimum password requirements
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

# Auto-lock timeout (seconds) - 0 to disable
# TODO: Make this a user setting
AUTO_LOCK_TIMEOUT = 0  # Disabled by default

# Session timeout after app goes to background (mobile)
BACKGROUND_LOCK_TIMEOUT = 300  # 5 minutes


COLORS = {
    "bg": "#1e1e1e",
    "sidebar": "#121212",
    "card": "#2d2d2d",
    "card_hover": "#383838",
    "accent": "#4a9eff",
    "input_bg": "#252525",
    "border": "#333",
    "danger": "#ff6b6b",
    "done_bg": "#1a1a1a",
    "done_text": "#666666",
    "unassigned": "#888888",
    "done_tag": "#3d3d3d",
    "white": "white",
    "green": "#4caf50",
    "blue": "#2196f3",
    "orange": "#ff9800",
    "gap_bg": "#1a2a1a",
    "gap_text": "#4a7a4a",
    # Stats chart colors (orange tones for estimates)
    "estimated_done": "#ef6c00",  # Medium-dark orange for completed estimates
    "estimated_pending": "#ff9800",  # Medium orange for pending estimates
}