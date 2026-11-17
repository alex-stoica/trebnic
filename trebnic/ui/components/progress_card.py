import flet as ft
from config import COLORS
from i18n import t
from services.scoring import progress


def progress_card(tasks, closed):
    p = progress(tasks, closed)
    return ft.Container(
        bgcolor=COLORS["card"], padding=20, border_radius=16,
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.INSIGHTS, color=COLORS["accent"]),
                ft.Text(t("score_level").format(level=p.level), size=24, weight="bold"),
                ft.Container(expand=True),
                ft.Text(f"{p.xp:.1f} XP", color=COLORS["accent"]),
            ]),
            ft.ProgressBar(value=p.fraction, color=COLORS["accent"], height=8, border_radius=4),
            ft.Text(t("score_next_level").format(points=f"{50 - p.xp % 50:.1f}", level=p.level + 1),
                    size=12, color=COLORS["done_text"]),
            ft.Divider(height=16),
            ft.Text(t("score_balance"), size=13, color=COLORS["done_text"]),
            ft.Text(f"{p.score:.1f} p", size=36, weight="bold",
                    color=COLORS["danger"] if p.score < 0 else COLORS["accent"]),
            ft.Text(t("score_breakdown").format(done=f"{p.completion:.1f}",
                effort=f"{p.effort:.1f}", failed=f"{p.penalties:.1f}"), size=13),
            ft.Text(t("score_rules"), size=12, color=COLORS["done_text"]),
        ], spacing=10, tight=True),
    )
