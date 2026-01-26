from typing import Dict
 
_current_language: str = "en"
 
LANGUAGES: Dict[str, Dict[str, str]] = {
    "en": {"name": "English", "flag": "🇬🇧", "code": "EN"},
    "ro": {"name": "Română", "flag": "🇷🇴", "code": "RO"},
}
 
_TRANSLATIONS: Dict[str, Dict[str, str]] = { 
    "profile": {"en": "Profile", "ro": "Profil"},
    "user": {"en": "User", "ro": "Utilizator"},
    "tap_photo_to_change": {"en": "Tap photo to change", "ro": "Atinge fotografia pentru a schimba"},
    "account_age": {"en": "Account age", "ro": "Vârsta contului"},
    "since": {"en": "Since", "ro": "Din"},
    "tasks_completed": {"en": "Tasks completed", "ro": "Treburi finalizate"},
    "total": {"en": "total", "ro": "total"},
    "most_active_project": {"en": "Most active project", "ro": "Cel mai activ proiect"},
    "none": {"en": "None", "ro": "Niciunul"},
    "preferences": {"en": "Preferences", "ro": "Preferințe"},
    "default_estimated_time": {"en": "Default estimated time", "ro": "Timp estimat implicit"},
    "notifications": {"en": "Notifications", "ro": "Notificări"},
    "email_weekly_stats": {"en": "Email weekly stats", "ro": "Statistici săptămânale pe email"},
    "save_preferences": {"en": "Save preferences", "ro": "Salvează preferințele"},
    "preferences_saved": {"en": "Preferences saved", "ro": "Preferințe salvate"},
    "factory_reset": {"en": "Factory reset", "ro": "Resetare totală"},
    "factory_reset_title": {"en": "⚠️ Factory Reset", "ro": "⚠️ Resetare totală"},
    "cannot_be_undone": {"en": "This action cannot be undone!", "ro": "Această acțiune nu poate fi anulată!"},
    "all_data_deleted": {
        "en": "All your tasks, projects, and settings will be permanently deleted.",
        "ro": "Toate treburile, proiectele și setările tale vor fi șterse permanent.",
    },
    "reset_everything": {"en": "Reset everything", "ro": "Resetează totul"},
    "all_data_reset": {"en": "All data has been reset", "ro": "Toate datele au fost resetate"},
    "language": {"en": "Language", "ro": "Limbă"},
    "reset_defaults": {"en": "Reset defaults", "ro": "Resetează la valorile implicite"},

    # Common buttons
    "cancel": {"en": "Cancel", "ro": "Anulează"},
    "save": {"en": "Save", "ro": "Salvează"},
    "create": {"en": "Create", "ro": "Creează"},
    "delete": {"en": "Delete", "ro": "Șterge"},
    "edit": {"en": "Edit", "ro": "Editează"},
    "add": {"en": "Add", "ro": "Adaugă"},
    "close": {"en": "Close", "ro": "Închide"},
    "confirm": {"en": "Confirm", "ro": "Confirmă"},
    "yes": {"en": "Yes", "ro": "Da"},
    "no": {"en": "No", "ro": "Nu"},
    "back": {"en": "Back", "ro": "Înapoi"},
    "select": {"en": "Select", "ro": "Selectează"},

    # Project dialogs
    "edit_project": {"en": "Edit project", "ro": "Editează proiect"},
    "create_new_project": {"en": "Create new project", "ro": "Creează proiect nou"},
    "select_icon": {"en": "Select icon", "ro": "Selectează iconiță"},
    "select_color": {"en": "Select color", "ro": "Selectează culoare"},
    "delete_project": {"en": "Delete project", "ro": "Șterge proiect"},
    "icon_label": {"en": "Icon:", "ro": "Iconiță:"},
    "color_label": {"en": "Color:", "ro": "Culoare:"},
    "project_name": {"en": "Project name", "ro": "Numele proiectului"},
    "project_updated": {"en": "Project '{name}' updated", "ro": "Proiectul '{name}' a fost actualizat"},
    "project_created": {"en": "Project '{name}' created", "ro": "Proiectul '{name}' a fost creat"},
    "project_deleted": {"en": "Project '{name}' deleted ({count} tasks removed)", "ro": "Proiectul '{name}' a fost șters ({count} treburi eliminate)"},
    "delete_project_confirm": {"en": "Delete '{name}' and all its tasks?", "ro": "Ștergi '{name}' și toate treburile sale?"},

    # Navigation
    "inbox": {"en": "Inbox", "ro": "La dospit"},
    "today": {"en": "Today", "ro": "Astăzi"},
    "calendar": {"en": "Calendar", "ro": "Calendar"},
    "upcoming": {"en": "Upcoming", "ro": "Viitoare"},
    "projects": {"en": "Projects", "ro": "Proiecte"},

    # Stats page
    "statistics": {"en": "Statistics", "ro": "Statistici"},
    "tasks_completed_stat": {"en": "Tasks completed", "ro": "Treburi finalizate"},
    "pending": {"en": "pending", "ro": "în așteptare"},
    "time_tracked": {"en": "Time tracked", "ro": "Timp înregistrat"},
    "tasks_with_time": {"en": "tasks with time", "ro": "treburi cu timp"},
    "estimation_accuracy": {"en": "Estimation accuracy", "ro": "Acuratețea estimării"},
    "taking_longer": {"en": "Taking longer than estimated", "ro": "Durează mai mult decât ai estimat"},
    "faster_than_estimated": {"en": "Faster than estimated", "ro": "Mai rapid decât estimat"},
    "on_target": {"en": "On target", "ro": "Conform estimării"},
    "no_data_yet": {"en": "No data yet", "ro": "Încă nu există date"},
    "longest_streak": {"en": "Longest streak", "ro": "Cea mai lungă serie"},
    "best_consecutive_run": {"en": "Best consecutive run", "ro": "Cea mai bună serie consecutivă"},
    "days": {"en": "days", "ro": "zile"},
    "day": {"en": "day", "ro": "zi"},
    "weekly_time": {"en": "Weekly time", "ro": "Timp săptămânal"},
    "tracked": {"en": "Tracked", "ro": "Înregistrat"},
    "est_done": {"en": "Est. done", "ro": "Est. finalizat"},
    "est_pending": {"en": "Est. pending", "ro": "Est. nefinalizat"},
    "estimated": {"en": "Estimated", "ro": "Estimat"},
    "previous_week": {"en": "Previous week", "ro": "Săptămâna anterioară"},
    "next_week": {"en": "Next week", "ro": "Săptămâna următoare"},
    "by_project": {"en": "By project", "ro": "Pe proiecte"},
    "tasks": {"en": "tasks", "ro": "treburi"},
    "complete": {"en": "complete", "ro": "finalizat"},
    "no_project_data": {"en": "No project data yet", "ro": "Încă nu există date despre proiecte"},
    "export_data": {"en": "Export data", "ro": "Exportă date"},
    "export_to_json": {"en": "Export to JSON", "ro": "Exportă în JSON"},
    "export_statistics": {"en": "Export statistics", "ro": "Exportă statistici"},
    "exported_to": {"en": "Exported to", "ro": "Exportat în"},
    "export_failed": {"en": "Export failed", "ro": "Exportul a eșuat"},
    "coming_soon": {"en": "Coming soon", "ro": "În curând"},
    "estimation_breakdown": {"en": "Estimation breakdown", "ro": "Detalii estimări"},
    "estimation_breakdown_desc": {
        "en": "See which tasks took longer vs faster",
        "ro": "Vezi care treburi au durat mai mult sau mai puțin",
    },
    "tooltip_tracked": {"en": "Tracked", "ro": "Înregistrat"},
    "tooltip_est_pending": {"en": "Est. pending", "ro": "Est. nefinalizat"},
    "tooltip_est_done": {"en": "Est. done", "ro": "Est. finalizat"},

    # Help page
    "how_to_use": {"en": "How to use Trebnic", "ro": "Cum să folosești Trebnic"},
    "privacy_first_title": {"en": "Privacy-first task manager", "ro": "Manager de treburi cu confidențialitate"},
    "privacy_first_desc": {
        "en": "Trebnic is built with your privacy at its core. All your data stays on your device - "
              "we never collect, track, or share any of your information. No accounts, no cloud sync, "
              "no analytics. Your tasks, your device, your privacy.",
        "ro": "Trebnic este construit cu confidențialitatea ta în centru. Toate datele tale rămân pe dispozitivul tău - "
              "nu colectăm, nu urmărim, nu partajăm niciodată informațiile tale. Fără conturi, fără sincronizare în cloud, "
              "fără analize. Treburile tale, dispozitivul tău, confidențialitatea ta.",
    },
    "works_offline": {"en": "Works offline", "ro": "Funcționează offline"},
    "optional_encryption": {"en": "Optional encryption", "ro": "Criptare opțională"},
    "no_tracking": {"en": "No tracking", "ro": "Fără urmărire"},
    "tasks_section": {"en": "Tasks", "ro": "Treburi"},
    "tasks_help_1": {
        "en": "Tap the + button to create a new task. Tap a task to mark it complete. "
              "Swipe right to start the timer, swipe left to delete.",
        "ro": "Apasă butonul + pentru a crea o treabă nouă. Apasă o treabă pentru a o marca ca finalizată. "
              "Glisează la dreapta pentru a porni cronometrul, glisează la stânga pentru a șterge.",
    },
    "tasks_help_2": {
        "en": "Long-press or tap the menu icon for more options: edit title, set due date, "
              "configure recurrence, view time stats, or move to a different project.",
        "ro": "Apasă lung sau apasă iconița de meniu pentru mai multe opțiuni: editare titlu, setare dată limită, "
              "configurare recurență, vizualizare statistici timp, sau mutare într-un alt proiect.",
    },
    "projects_section": {"en": "Projects", "ro": "Proiecte"},
    "projects_help_1": {
        "en": "Use the sidebar to organize tasks into projects. Tap a project to filter tasks. "
              "Create new projects from the sidebar menu. Each project can have its own icon and color.",
        "ro": "Folosește bara laterală pentru a organiza treburile în proiecte. Apasă un proiect pentru a filtra treburile. "
              "Creează proiecte noi din meniul barei laterale. Fiecare proiect poate avea propria iconiță și culoare.",
    },
    "projects_help_2": {
        "en": "Project filtering combines with your current view. For example, selecting 'Today' in the "
              "navigation and then a project shows only today's tasks from that project. This lets you "
              "focus on what matters right now.",
        "ro": "Filtrarea pe proiecte se combină cu vizualizarea curentă. De exemplu, selectând 'Astăzi' în "
              "navigare și apoi un proiect arată doar treburile de azi din acel proiect. Astfel te poți "
              "concentra pe ce contează acum.",
    },
    "time_tracking_section": {"en": "Time tracking", "ro": "Înregistrarea timpului"},
    "time_tracking_help_1": {
        "en": "Track how much time you spend on each task. Start the timer by swiping right on a task "
              "or from the task menu.",
        "ro": "Vezi cât timp petreci în fiecare treabă. Pornește cronometrul glisând la dreapta pe o treabă "
              "sau din meniul ei.",
    },
    "time_tracking_help_2": {
        "en": "The active timer appears in the header showing elapsed time and task name. Tap the timer "
              "to stop it or switch to a different task. You can only have one timer running at a time.",
        "ro": "Cronometrul activ apare în antet arătând timpul scurs și numele trebii. Apasă cronometrul "
              "pentru a-l opri sau a trece la altă treabă. Poți avea un singur cronometru activ la un moment dat.",
    },
    "time_tracking_help_3": {
        "en": "View your time history for any task from the task menu. All time entries are stored locally "
              "and can be used to understand how you spend your time.",
        "ro": "Vezi istoricul timpului pentru orice treabă din meniul ei. Toate înregistrările de timp sunt "
              "stocate local și pot fi folosite pentru a înțelege cum îți petreci timpul.",
    },
    "recurring_section": {"en": "Recurring tasks", "ro": "Treburi recurente"},
    "recurring_help_1": {
        "en": "Set tasks to repeat automatically. From the task menu, select 'Recurrence' to configure "
              "how often the task should repeat.",
        "ro": "Setează treburile să se repete automat. Din meniul trebii, selectează 'Recurență' pentru a configura "
              "cât de des să se repete treaba.",
    },
    "recurring_help_2": {
        "en": "Choose from daily, weekly, or monthly intervals. For example: every 2 days, every week, "
              "or every 3 months. You can also select specific days of the week for weekly recurrence.",
        "ro": "Alege între intervale zilnice, săptămânale sau lunare. De exemplu: la fiecare 2 zile, în fiecare săptămână, "
              "sau la fiecare 3 luni. Poți selecta și zile specifice ale săptămânii pentru recurența săptămânală.",
    },
    "recurring_help_3": {
        "en": "When you complete a recurring task, it automatically reschedules to the next occurrence. "
              "The next due date is calculated based on your recurrence settings, ensuring you never "
              "miss a repeated task.",
        "ro": "Când finalizezi o treabă recurentă, aceasta se reprogramează automat la următoarea apariție. "
              "Data limită următoare este calculată pe baza recurenței, asigurându-te că nu "
              "ratezi niciodată o treabă repetitivă.",
    },
    "calendar_section": {"en": "Calendar view", "ro": "Vizualizare calendar"},
    "calendar_help_1": {
        "en": "View tasks organized by week. Swipe left or right to navigate between weeks. "
              "Tasks are shown on their due dates, helping you plan ahead.",
        "ro": "Vezi treburile organizate pe săptămâni. Glisează la stânga sau la dreapta pentru a naviga între săptămâni. "
              "Treburile sunt afișate la datele lor limită, ajutându-te să planifici din timp.",
    },
    "security_section": {"en": "Security and encryption", "ro": "Securitate și criptare"},
    "security_help_1": {
        "en": "For extra privacy, enable encryption in Settings to protect sensitive data with a "
              "master password. Task titles, notes, and project names are encrypted using AES-256-GCM.",
        "ro": "Pentru confidențialitate suplimentară, activează criptarea în Setări pentru a proteja datele sensibile cu o "
              "parolă principală. Titlurile treburilor, notițele și numele proiectelor sunt criptate folosind AES-256-GCM.",
    },
    "security_help_2": {
        "en": "Your master password never leaves your device and is never stored - only a verification "
              "hash is kept to confirm you entered the correct password. On supported devices, use "
              "fingerprint or face unlock for convenient access.",
        "ro": "Parola ta principală nu părăsește niciodată dispozitivul și nu este stocată - doar un hash de verificare "
              "este păstrat pentru a confirma că ai introdus parola corectă. Pe dispozitivele compatibile, folosește "
              "amprenta sau deblocarea facială pentru acces convenabil.",
    },
    "feedback_link": {"en": "Have feedback or want to support Trebnic?", "ro": "Ai feedback sau vrei să susții Trebnic?"},
    "motivational_footer": {
        "en": "Don't be NETrebnic - be Trebnic and get your tasks done!",
        "ro": "Nu fi NETrebnic - fii Trebnic și termină-ți treburile!",
    },

    # Feedback page
    "feedback_and_support": {"en": "Feedback and support", "ro": "Feedback și suport"},
    "support_trebnic": {"en": "Support Trebnic", "ro": "Susține Trebnic"},
    "support_desc_1": {
        "en": "Trebnic is designed to be free, private, and offline-first. We don't track you or sell your data.",
        "ro": "Trebnic este conceput să fie gratuit, privat și offline-first. Nu te urmărim și nu vindem datele tale.",
    },
    "support_desc_2": {
        "en": "Development and maintenance costs are supported by users like you. "
              "If you find this app useful, please consider making a donation.",
        "ro": "Costurile de dezvoltare și întreținere sunt susținute de utilizatori ca tine. "
              "Dacă îți este utilă aplicația, te rugăm să iei în calcul o donație.",
    },
    "make_donation": {"en": "Make a donation", "ro": "Fă o donație"},
    "category": {"en": "Category", "ro": "Categorie"},
    "issue": {"en": "Issue", "ro": "Problemă"},
    "feature_request": {"en": "Feature request", "ro": "Funcționalitate nouă"},
    "other": {"en": "Other", "ro": "Altele"},
    "message": {"en": "Message", "ro": "Mesaj"},
    "message_hint": {"en": "Describe the issue or feature request...", "ro": "Descrie problema sau cererea de funcționalitate..."},
    "send_feedback": {"en": "Send feedback", "ro": "Trimite feedback"},
    "found_bug": {"en": "Found a bug? Have an idea? Let us know!", "ro": "Ai găsit un bug? Ai o idee? Spune-ne!"},
    "feedback_sent": {"en": "Feedback sent, thank you!", "ro": "Feedback trimis, mulțumim!"},
    "feedback_failed": {"en": "Failed", "ro": "Eșuat"},
    "network_error": {"en": "Network error", "ro": "Eroare de rețea"},
    "please_enter_message": {"en": "Please enter a message", "ro": "Te rugăm să introduci un mesaj"},
    "sending_feedback": {"en": "Sending feedback...", "ro": "Se trimite feedback..."},
    "feedback_not_configured": {"en": "Feedback not configured. Check .env file.", "ro": "Feedback neconfigurat. Verifică fișierul .env."},
    "need_help_link": {"en": "Need help using Trebnic? View the guide", "ro": "Ai nevoie de ajutor cu Trebnic? Vezi ghidul"},

    # Task view
    "all_caught_up": {"en": "All caught up!", "ro": "Totul la zi!"},
    "enjoy_your_day": {"en": "Enjoy your day!", "ro": "Bucură-te de ziua ta!"},
    "add_details": {"en": "Add details", "ro": "Detalii"},
    "add_details_tooltip": {"en": "Click to add tags, due date, and more", "ro": "Click pentru a adăuga etichete, dată limită și altele"},
    "add_new_task": {"en": "Add a new task...", "ro": "Pune o treabă nouă..."},
    "estimated_time": {"en": "Estimated time", "ro": "Timp estimat"},
    "time_range_hint": {"en": "5 min - 8 hrs 20 min", "ro": "5 min - 8 ore 20 min"},
    "task_details": {"en": "Task details", "ro": "Detalii treabă"},
    "section_today": {"en": "TODAY", "ro": "ASTĂZI"},
    "section_inbox": {"en": "INBOX", "ro": "LA DOSPIT"},
    "section_upcoming": {"en": "UPCOMING", "ro": "VIITOARE"},
    "section_tasks": {"en": "TASKS", "ro": "TREBURI"},
    "section_done": {"en": "DONE", "ro": "GATA"},

    # Calendar view
    "day_mon": {"en": "Mon", "ro": "Lun"},
    "day_tue": {"en": "Tue", "ro": "Mar"},
    "day_wed": {"en": "Wed", "ro": "Mie"},
    "day_thu": {"en": "Thu", "ro": "Joi"},
    "day_fri": {"en": "Fri", "ro": "Vin"},
    "day_sat": {"en": "Sat", "ro": "Sâm"},
    "day_sun": {"en": "Sun", "ro": "Dum"},

    # Time entries view
    "today_label": {"en": "Today", "ro": "Astăzi"},
    "yesterday_label": {"en": "Yesterday", "ro": "Ieri"},
    "cannot_edit_running": {"en": "Cannot edit a running timer", "ro": "Nu poți edita un cronometru în curs"},
    "start_time_fixed": {"en": "Start time (fixed)", "ro": "Ora de început (fixată)"},
    "end_time": {"en": "End time", "ro": "Ora de sfârșit"},
    "time_entry_updated": {"en": "Time entry updated", "ro": "Înregistrare actualizată"},
    "edit_time_entry": {"en": "Edit time entry", "ro": "Editează înregistrarea"},
    "now": {"en": "Now", "ro": "Acum"},
    "no_project": {"en": "No project", "ro": "Fără proiect"},
    "click_to_edit": {"en": "Click to edit", "ro": "Click pentru a edita"},
    "delete_entry": {"en": "Delete entry", "ro": "Șterge înregistrarea"},
    "work_time": {"en": "Work time", "ro": "Timp de lucru"},
    "break_time": {"en": "Break time", "ro": "Timp de pauză"},
    "efficiency": {"en": "Efficiency", "ro": "Eficiență"},
    "break_label": {"en": "Break", "ro": "Pauză"},
    "no_time_entries": {"en": "No time entries yet", "ro": "Încă nu există înregistrări de timp"},
    "start_timer_hint": {"en": "Start a timer on this task to track your time", "ro": "Pornește un cronometru pe această treabă pentru a-ți înregistra timpul"},
    "time_entries_title": {"en": "Time entries", "ro": "Înregistrări de timp"},
    "total_label": {"en": "Total", "ro": "Total"},
    "click_duration_hint": {"en": "Click duration to edit", "ro": "Click pe durată pentru a edita"},
    "unknown_task": {"en": "Unknown task", "ro": "Treabă necunoscută"},
    "entry_singular": {"en": "entry", "ro": "înregistrare"},
    "entries_plural": {"en": "entries", "ro": "înregistrări"},
    "break_singular": {"en": "break", "ro": "pauză"},
    "breaks_plural": {"en": "breaks", "ro": "pauze"},
    "time_entry_deleted": {"en": "Time entry deleted", "ro": "Înregistrare de timp ștearsă"},

    # Profile
    "select_profile_photo": {"en": "Select profile photo", "ro": "Selectează fotografia de profil"},

    # Menu
    "menu_stats": {"en": "Stats", "ro": "Statistici"},
    "menu_encryption": {"en": "Encryption", "ro": "Criptare"},
    "menu_help": {"en": "Help", "ro": "Ajutor"},
    "menu_logout": {"en": "Logout", "ro": "Deconectare"},

    # Auth dialogs
    "encryption_settings": {"en": "Encryption settings", "ro": "Setări de criptare"},
}


def get_language() -> str:
    """Get the current language code."""
    return _current_language


def set_language(lang: str) -> None:
    """Set the current language. Call this when AppState.language changes."""
    global _current_language
    if lang in LANGUAGES:
        _current_language = lang


def t(key: str) -> str:
    """Get translated string for the given key.

    Falls back to English if translation not found for current language.
    Falls back to the key itself if not found in any language.
    """
    if key not in _TRANSLATIONS:
        return key

    translations = _TRANSLATIONS[key]

    # Try current language first
    if _current_language in translations:
        return translations[_current_language]

    # Fallback to English
    if "en" in translations:
        return translations["en"]

    # Last resort: return key
    return key
