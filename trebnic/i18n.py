"""Internationalization module - provides t("key") for translated strings.

All user-facing text must use t("key") to support multiple languages (EN/RO).
Add new translations to _TRANSLATIONS dict with both "en" and "ro" values.
"""
from typing import Dict

_current_language: str = "en"
 
LANGUAGES: Dict[str, Dict[str, str]] = {
    "en": {"name": "English", "flag": "🇺🇸", "code": "EN"},
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
    "project_deleted": {
        "en": "Project '{name}' deleted ({count} tasks removed)",
        "ro": "Proiectul '{name}' a fost șters ({count} treburi eliminate)",
    },
    "delete_project_confirm": {
        "en": "Delete '{name}' and all its tasks?",
        "ro": "Ștergi '{name}' și toate treburile sale?",
    },

    # Navigation
    "inbox": {"en": "Draft", "ro": "La dospit"},
    "today": {"en": "Today", "ro": "Astăzi"},
    "tasks_nav": {"en": "Tasks", "ro": "Treburi"},
    "next": {"en": "Next", "ro": "Viitoare"},
    "calendar": {"en": "Calendar", "ro": "Calendar"},
    "upcoming": {"en": "Upcoming", "ro": "Viitoare"},
    "notes": {"en": "Notes", "ro": "Notițe"},
    "projects": {"en": "Projects", "ro": "Proiecte"},

    # Stats page
    "statistics": {"en": "Statistics", "ro": "Statistici"},
    "tasks_completed_stat": {"en": "Tasks completed", "ro": "Treburi finalizate"},
    "pending": {"en": "pending", "ro": "în așteptare"},
    "time_tracked": {"en": "Time tracked", "ro": "Timp înregistrat"},
    "tasks_with_estimates": {"en": "tasks with estimates", "ro": "treburi cu estimare"},
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
    "est_pending": {"en": "Est. pending", "ro": "Est. în aștept."},
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
        "en": (
            "Trebnic is built with your privacy at its core. All your data stays on your device - "
            "we never collect, track, or share any of your information. No accounts, no cloud sync, "
            "no analytics. Your tasks, your device, your privacy."
        ),
        "ro": (
            "Trebnic este construit cu confidențialitatea ta în centru. Toate datele tale rămân "
            "pe dispozitivul tău - nu colectăm, nu urmărim, nu partajăm niciodată informațiile tale. "
            "Fără conturi, fără sincronizare în cloud, fără analize. Treburile tale, dispozitivul "
            "tău, confidențialitatea ta."
        ),
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
        "en": (
            "Long-press or tap the menu icon for more options: edit title, set due date, "
            "configure recurrence, view time stats, or move to a different project."
        ),
        "ro": (
            "Apasă lung sau apasă iconița de meniu pentru mai multe opțiuni: editare titlu, "
            "setare dată limită, configurare recurență, vizualizare statistici timp, sau "
            "mutare într-un alt proiect."
        ),
    },
    "projects_section": {"en": "Projects", "ro": "Proiecte"},
    "projects_help_1": {
        "en": "Use the sidebar to organize tasks into projects. Tap a project to filter tasks. "
              "Create new projects from the sidebar menu. Each project can have its own icon and color.",
        "ro": (
            "Folosește bara laterală pentru a organiza treburile în proiecte. Apasă un proiect "
            "pentru a filtra treburile. Creează proiecte noi din meniul barei laterale. Fiecare "
            "proiect poate avea propria iconiță și culoare."
        ),
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
        "ro": (
            "Alege între intervale zilnice, săptămânale sau lunare. De exemplu: la fiecare 2 zile, "
            "în fiecare săptămână, sau la fiecare 3 luni. Poți selecta și zile specifice ale "
            "săptămânii pentru recurența săptămânală."
        ),
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
        "ro": (
            "Vezi treburile organizate pe săptămâni. Glisează la stânga sau la dreapta pentru a "
            "naviga între săptămâni. Treburile sunt afișate la datele lor limită, ajutându-te să "
            "planifici din timp."
        ),
    },
    "security_section": {"en": "Security and encryption", "ro": "Securitate și criptare"},
    "security_help_1": {
        "en": "For extra privacy, enable encryption in Settings to protect sensitive data with a "
              "master password. Task titles, daily notes, and project names are encrypted using AES-256-GCM.",
        "ro": (
            "Pentru confidențialitate suplimentară, activează criptarea în Setări pentru a proteja "
            "datele sensibile cu o parolă principală. Titlurile treburilor, notițele zilnice și numele "
            "proiectelor sunt criptate folosind AES-256-GCM."
        ),
    },
    "security_help_2": {
        "en": "Your master password never leaves your device and is never stored - only a verification "
              "hash is kept to confirm you entered the correct password. On supported devices, use "
              "fingerprint or face unlock for convenient access.",
        "ro": (
            "Parola ta principală nu părăsește niciodată dispozitivul și nu este stocată - doar un "
            "hash de verificare este păstrat pentru a confirma că ai introdus parola corectă. Pe "
            "dispozitivele compatibile, folosește amprenta sau deblocarea facială pentru acces "
            "convenabil."
        ),
    },
    "feedback_link": {
        "en": "Have feedback or want to support Trebnic?",
        "ro": "Ai feedback sau vrei să susții Trebnic?",
    },
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
    "message_hint": {
        "en": "Describe the issue or feature request...",
        "ro": "Descrie problema sau cererea de funcționalitate...",
    },
    "send_feedback": {"en": "Send feedback", "ro": "Trimite feedback"},
    "found_bug": {"en": "Found a bug? Have an idea? Let us know!", "ro": "Ai găsit un bug? Ai o idee? Spune-ne!"},
    "feedback_sent": {"en": "Feedback sent, thank you!", "ro": "Feedback trimis, mulțumim!"},
    "feedback_failed": {"en": "Failed", "ro": "Eșuat"},
    "error_generic": {"en": "Error: {error}", "ro": "Eroare: {error}"},
    "network_error": {"en": "Network error", "ro": "Eroare de rețea"},
    "please_enter_message": {"en": "Please enter a message", "ro": "Te rugăm să introduci un mesaj"},
    "sending_feedback": {"en": "Sending feedback...", "ro": "Se trimite feedback..."},
    "feedback_not_configured": {
        "en": "Feedback not configured. Set up your API key below.",
        "ro": "Feedback neconfigurat. Configurează cheia API mai jos.",
    },
    "email_config": {"en": "Email configuration", "ro": "Configurare email"},
    "email_config_desc": {
        "en": "Configure your Resend API key to enable feedback",
        "ro": "Configurează cheia API Resend pentru a activa feedback-ul",
    },
    "resend_api_key": {"en": "Resend API key", "ro": "Cheie API Resend"},
    "feedback_email_label": {"en": "Feedback email", "ro": "Email feedback"},
    "config_saved": {"en": "Configuration saved", "ro": "Configurare salvată"},
    "configured": {"en": "Configured", "ro": "Configurat"},
    "not_configured": {"en": "Not configured", "ro": "Neconfigurat"},
    "need_help_link": {
        "en": "Need help using Trebnic? View the guide",
        "ro": "Ai nevoie de ajutor cu Trebnic? Vezi ghidul",
    },

    # Task view
    "all_caught_up": {"en": "All caught up!", "ro": "Totul la zi!"},
    "enjoy_your_day": {"en": "Enjoy your day!", "ro": "Bucură-te de ziua ta!"},
    "add_details": {"en": "Add details", "ro": "Detalii"},
    "add_details_tooltip": {
        "en": "Click to add tags, due date, and more",
        "ro": "Click pentru a adăuga etichete, dată limită și altele",
    },
    "add_new_task": {"en": "Add a new task...", "ro": "Pune o treabă nouă..."},
    "estimated_time": {"en": "Estimated time", "ro": "Timp estimat"},
    "time_range_hint": {"en": "5 min - 8 hrs 20 min", "ro": "5 min - 8 ore 20 min"},
    "task_details": {"en": "Task details", "ro": "Detalii treabă"},
    "section_today": {"en": "TODAY", "ro": "ASTĂZI"},
    "section_inbox": {"en": "DRAFT", "ro": "LA DOSPIT"},
    "section_upcoming": {"en": "UPCOMING", "ro": "VIITOARE"},
    "section_next": {"en": "NEXT", "ro": "VIITOARE"},
    "section_tasks": {"en": "TASKS", "ro": "TREBURI"},
    "section_done": {"en": "DONE", "ro": "GATA"},
    "section_overdue": {"en": "OVERDUE", "ro": "RESTANTE"},
    "section_overdue_count": {"en": "OVERDUE ({count})", "ro": "RESTANTE ({count})"},

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
    "start_timer_hint": {
        "en": "Start a timer on this task to track your time",
        "ro": "Pornește un cronometru pe această treabă pentru a-ți înregistra timpul",
    },
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
    "encryption_enabled": {"en": "Encryption is enabled", "ro": "Criptarea este activată"},
    "encryption_not_enabled": {"en": "Encryption is not enabled", "ro": "Criptarea nu este activată"},
    "encryption_not_enabled_desc": {
        "en": "Enable encryption to protect your tasks, daily notes, and project names with a master password.",
        "ro": (
            "Activează criptarea pentru a-ți proteja treburile, notițele zilnice și numele proiectelor "
            "cu o parolă principală."
        ),
    },
    "set_up_encryption": {"en": "Set up encryption", "ro": "Configurează criptarea"},
    "change_password": {"en": "Change password", "ro": "Schimbă parola"},
    "update_master_password": {"en": "Update your master password", "ro": "Actualizează parola principală"},
    "biometric_unlock": {"en": "Biometric unlock", "ro": "Deblocare biometrică"},
    "biometric_unlock_desc": {
        "en": "Use Face ID / Touch ID / fingerprint",
        "ro": "Folosește Face ID / Touch ID / amprentă",
    },
    "disable_encryption": {"en": "Disable encryption", "ro": "Dezactivează criptarea"},
    "disable_encryption_warning": {
        "en": "This will permanently remove encryption from all your data.",
        "ro": "Aceasta va elimina permanent criptarea de pe toate datele tale.",
    },
    "disable_encryption_desc": {
        "en": "Your data will be decrypted and stored as plain text. Enter your master password to confirm.",
        "ro": "Datele tale vor fi decriptate și stocate ca text simplu. Introdu parola principală pentru a confirma.",
    },
    "enter_password_to_confirm": {
        "en": "Enter password to confirm",
        "ro": "Introdu parola pentru a confirma",
    },
    "encryption_disabled": {
        "en": "Encryption has been disabled",
        "ro": "Criptarea a fost dezactivată",
    },
    "create_password": {"en": "Create password", "ro": "Creează parola"},
    "choose_strong_password": {"en": "Choose a strong password", "ro": "Alege o parolă puternică"},
    "confirm_password": {"en": "Confirm password", "ro": "Confirmă parola"},
    "enter_password_again": {"en": "Enter password again", "ro": "Introdu parola din nou"},
    "protect_data_with_encryption": {
        "en": "Protect your data with encryption",
        "ro": "Protejează-ți datele cu criptare",
    },
    "master_password_desc": {
        "en": "Your master password encrypts all sensitive data. It's never stored - only you know it.",
        "ro": "Parola ta principală criptează toate datele sensibile. Nu este stocată niciodată - doar tu o știi.",
    },
    "password_forget_warning": {
        "en": "If you forget this password, your data cannot be recovered!",
        "ro": "Dacă uiți această parolă, datele tale nu pot fi recuperate!",
    },
    "skip_for_now": {"en": "Skip for now", "ro": "Sari peste"},
    "enable_encryption": {"en": "Enable encryption", "ro": "Activează criptarea"},
    "passwords_do_not_match": {"en": "Passwords do not match", "ro": "Parolele nu se potrivesc"},
    "setup_failed": {"en": "Setup failed", "ro": "Configurarea a eșuat"},
    "password_min_length": {
        "en": "Password must be at least {length} characters",
        "ro": "Parola trebuie să aibă cel puțin {length} caractere",
    },
    "password_max_length": {
        "en": "Password must be at most {length} characters",
        "ro": "Parola trebuie să aibă cel mult {length} caractere",
    },
    "password_needs_uppercase": {
        "en": "Password must contain at least one uppercase letter",
        "ro": "Parola trebuie să conțină cel puțin o literă mare",
    },
    "password_needs_lowercase": {
        "en": "Password must contain at least one lowercase letter",
        "ro": "Parola trebuie să conțină cel puțin o literă mică",
    },
    "password_needs_digit": {
        "en": "Password must contain at least one digit",
        "ro": "Parola trebuie să conțină cel puțin o cifră",
    },
    "master_password": {"en": "Master password", "ro": "Parola principală"},
    "enter_master_password": {"en": "Enter your master password", "ro": "Introdu parola ta principală"},
    "please_enter_password": {"en": "Please enter your password", "ro": "Te rugăm să introduci parola"},
    "incorrect_password": {"en": "Incorrect password", "ro": "Parolă incorectă"},
    "your_data_is_encrypted": {"en": "Your data is encrypted", "ro": "Datele tale sunt criptate"},
    "unlock": {"en": "Unlock", "ro": "Deblochează"},
    "unlock_trebnic": {"en": "Unlock Trebnic", "ro": "Deblochează Trebnic"},
    "current_password": {"en": "Current password", "ro": "Parola curentă"},
    "new_password": {"en": "New password", "ro": "Parola nouă"},
    "confirm_new_password": {"en": "Confirm new password", "ro": "Confirmă parola nouă"},
    "please_enter_current_password": {
        "en": "Please enter your current password",
        "ro": "Te rugăm să introduci parola curentă",
    },
    "new_passwords_do_not_match": {"en": "New passwords do not match", "ro": "Parolele noi nu se potrivesc"},
    "current_password_incorrect": {"en": "Current password is incorrect", "ro": "Parola curentă este incorectă"},
    "failed": {"en": "Failed", "ro": "Eșuat"},
    "change_master_password": {"en": "Change master password", "ro": "Schimbă parola principală"},
    "password_changed": {"en": "Password changed successfully", "ro": "Parola a fost schimbată cu succes"},

    # Notification settings
    "notification_settings": {"en": "Notification settings", "ro": "Setări notificări"},
    "notifications_enabled": {"en": "Enable notifications", "ro": "Activează notificările"},
    "notify_due_reminders": {"en": "Due date reminders", "ro": "Memento dată limită"},
    "notify_due_reminders_desc": {"en": "Remind before tasks are due", "ro": "Amintește înainte de termenul limită"},
    "reminder_minutes_before": {"en": "Remind before due", "ro": "Amintește înainte de termen"},
    "reminder_1h_before": {"en": "1h before", "ro": "Cu 1h înainte"},
    "reminder_6h_before": {"en": "6h before", "ro": "Cu 6h înainte"},
    "reminder_12h_before": {"en": "12h before", "ro": "Cu 12h înainte"},
    "reminder_24h_before": {"en": "24h before", "ro": "Cu 24h înainte"},
    "custom_reminder": {"en": "Custom reminder", "ro": "Memento personalizat"},
    "minutes_before": {"en": "{minutes} min before", "ro": "Cu {minutes} min înainte"},
    "hours_before": {"en": "{hours}h before", "ro": "Cu {hours}h înainte"},
    "test_notification": {"en": "Test notification", "ro": "Notificare test"},
    "test_notification_title": {"en": "Test notification", "ro": "Notificare test"},
    "test_notification_body": {"en": "Notifications are working!", "ro": "Notificările funcționează!"},
    "test_notification_mobile_only": {
        "en": "Test notifications are only available on mobile",
        "ro": "Notificările de test sunt disponibile doar pe mobil",
    },
    "test_notification_unavailable": {
        "en": "Notifications are not available on this device",
        "ro": "Notificările nu sunt disponibile pe acest dispozitiv",
    },
    "notify_overdue": {"en": "Overdue task alerts", "ro": "Alerte treburi restante"},
    "overdue_notification_title": {"en": "Overdue tasks", "ro": "Treburi restante"},
    "overdue_notification_body_one": {"en": "You have 1 overdue task", "ro": "Ai 1 treabă restantă"},
    "overdue_notification_body_many": {"en": "You have {count} overdue tasks", "ro": "Ai {count} treburi restante"},
    "test_notification_sent": {"en": "Notification sent", "ro": "Notificare trimisă"},
    "test_notification_failed": {"en": "Notification delivery failed", "ro": "Trimiterea notificării a eșuat"},
    "notification_permission_denied": {"en": "Notification permission denied", "ro": "Permisiune notificări refuzată"},
    "notification_permission_granted": {"en": "Notifications enabled", "ro": "Notificări activate"},
    "task_reminder": {"en": "Task reminder", "ro": "Memento treabă"},
    "unlock_to_see_details": {"en": "Unlock Trebnic to see details", "ro": "Deblochează Trebnic pentru detalii"},
    "timer_complete": {"en": "Timer complete", "ro": "Cronometru finalizat"},
    "tracked_time_on_task": {"en": "Tracked {time} on {task}", "ro": "{time} înregistrat pe {task}"},
    "task_due_in": {"en": "\"{task}\" is due in {time}", "ro": "\"{task}\" scade în {time}"},
    "notif_action_complete": {"en": "Complete", "ro": "Finalizează"},
    "notif_action_postpone": {"en": "Postpone", "ro": "Amână"},
    "task_completed_via_notification": {
        "en": "'{title}' completed",
        "ro": "'{title}' finalizat(ă)",
    },
    "task_postponed_via_notification": {
        "en": "'{title}' postponed to {date}",
        "ro": "'{title}' amânat(ă) la {date}",
    },

    # Timer controller
    "stop_current_timer_first": {
        "en": "Stop current timer first",
        "ro": "Oprește cronometrul curent mai întâi",
    },
    "timer_started_for": {
        "en": "Timer started for '{title}'",
        "ro": "Cronometru pornit pentru '{title}'",
    },
    "timer_recovered": {
        "en": "Timer recovered for '{title}' ({time} elapsed)",
        "ro": "Cronometru recuperat pentru '{title}' ({time} scurs)",
    },
    "timer_discarded": {
        "en": "Timer discarded - minimum recorded time is {minutes} minutes",
        "ro": "Cronometru anulat - timpul minim înregistrat este de {minutes} minute",
    },
    "time_added_to_task": {
        "en": "Added {time} to '{title}'",
        "ro": "{time} adăugat la '{title}'",
    },

    # Task action handler
    "next_occurrence_scheduled": {
        "en": "Next occurrence scheduled for {date}",
        "ro": "Următoarea apariție programată pentru {date}",
    },
    "failed_to_delete_task": {
        "en": "Failed to delete task: {error}",
        "ro": "Nu s-a putut șterge treaba: {error}",
    },
    "task_deleted_single": {
        "en": "'{title}' deleted",
        "ro": "'{title}' șters(ă)",
    },
    "failed_to_delete_tasks": {
        "en": "Failed to delete tasks: {error}",
        "ro": "Nu s-au putut șterge treburile: {error}",
    },
    "deleted_one_occurrence": {
        "en": "Deleted 1 '{title}' occurrence",
        "ro": "1 apariție a '{title}' ștearsă",
    },
    "deleted_n_occurrences": {
        "en": "Deleted {count} '{title}' occurrences",
        "ro": "{count} apariții ale '{title}' șterse",
    },
    "failed_to_duplicate_task": {
        "en": "Failed to duplicate task: {error}",
        "ro": "Nu s-a putut duplica treaba: {error}",
    },
    "task_duplicated_as": {
        "en": "Task duplicated as '{title}'",
        "ro": "Treabă duplicată ca '{title}'",
    },
    "failed_to_postpone_task": {
        "en": "Failed to postpone task: {error}",
        "ro": "Nu s-a putut amâna treaba: {error}",
    },
    "task_postponed_to": {
        "en": "'{title}' postponed to {date}",
        "ro": "'{title}' amânat(ă) la {date}",
    },
    "task_postponed_to_upcoming": {
        "en": "'{title}' postponed to {date} (see Upcoming)",
        "ro": "'{title}' amânat(ă) la {date} (vezi Viitoare)",
    },

    # Task tile - menu items and labels
    "encrypted": {"en": "Encrypted", "ro": "Criptat"},
    "unassigned": {"en": "Unassigned", "ro": "Neatribuit"},
    "start_timer": {"en": "Start timer", "ro": "Pornește cronometru"},
    "rename": {"en": "Rename", "ro": "Redenumește"},
    "reschedule": {"en": "Reschedule", "ro": "Reprogramează"},
    "postpone_by_1_day": {"en": "Postpone by 1 day", "ro": "Amână cu 1 zi"},
    "set_recurrence": {"en": "Set recurrence", "ro": "Setează recurența"},
    "duplicate_task": {"en": "Duplicate task", "ro": "Duplică treaba"},
    "stats": {"en": "Stats", "ro": "Statistici"},
    "task_options": {"en": "Task options", "ro": "Opțiuni treabă"},

    # Timer widget
    "click_to_stop_timer": {
        "en": "Click to stop timer",
        "ro": "Click pentru a opri cronometrul",
    },

    # Task dialogs - Rename
    "rename_task": {"en": "Rename task", "ro": "Redenumește treaba"},
    "task_name_exists": {
        "en": "A task with this name already exists",
        "ro": "O treabă cu acest nume există deja",
    },
    "renamed_to": {"en": "Renamed to '{name}'", "ro": "Redenumit în '{name}'"},

    # Task dialogs - Assign project
    "assign_to_project": {"en": "Assign to project", "ro": "Atribuie proiectului"},
    "unassign": {"en": "Unassign", "ro": "Dezatribuie"},
    "task_assigned_to": {
        "en": "Task assigned to {name}",
        "ro": "Treabă atribuită la {name}",
    },

    # Task dialogs - Date picker
    "select_date": {"en": "Select date", "ro": "Selectează data"},
    "recurrent_tasks_use_pattern": {
        "en": "Recurrent tasks use their recurrence pattern.",
        "ro": "Treburile recurente folosesc modelul de recurență.",
    },
    "edit_recurrence_to_change": {
        "en": "Edit recurrence settings to change schedule.",
        "ro": "Editează setările de recurență pentru a schimba programul.",
    },
    "no_due_date": {"en": "🚫 No due date", "ro": "🚫 Fără dată limită"},
    "tomorrow": {"en": "Tomorrow", "ro": "Mâine"},
    "pick_a_date": {"en": "Pick a date...", "ro": "Alege o dată..."},
    "due_date_cleared": {"en": "Due date cleared", "ro": "Dată limită ștearsă"},
    "task_moved_to_draft": {
        "en": "Task moved to Draft",
        "ro": "Treabă mutată la Dospit",
    },
    "date_set_to": {"en": "Date set to {date}", "ro": "Dată setată la {date}"},
    "date_set_to_see_today": {
        "en": "Date set to {date} (see Today)",
        "ro": "Dată setată la {date} (vezi Astăzi)",
    },
    "date_set_to_see_upcoming": {
        "en": "Date set to {date} (see Next)",
        "ro": "Dată setată la {date} (vezi Viitoare)",
    },

    # Task dialogs - Recurrence
    "on_these_days": {"en": "On these days", "ro": "În aceste zile"},
    "freq_days": {"en": "Days", "ro": "Zile"},
    "freq_weeks": {"en": "Weeks", "ro": "Săptămâni"},
    "freq_months": {"en": "Months", "ro": "Luni"},
    "enable_recurrence": {"en": "Enable recurrence", "ro": "Activează recurența"},
    "never": {"en": "Never", "ro": "Niciodată"},
    "on_date": {"en": "On date", "ro": "La data"},
    "recur_from_completion": {
        "en": "Recur from completion date",
        "ro": "Recurent de la data finalizării",
    },
    "frequency_label": {"en": "Frequency", "ro": "Frecvență"},
    "repeat_every": {"en": "Repeat every", "ro": "Repetă la fiecare"},
    "behavior": {"en": "Behavior", "ro": "Comportament"},
    "from_completion_explanation": {
        "en": "When enabled, the next occurrence is calculated from the "
              "completion date instead of the original due date. "
              "Useful for habits like 'Every 30 days'.",
        "ro": "Când este activat, următoarea apariție este calculată de la "
              "data finalizării în loc de data limită originală. "
              "Util pentru obiceiuri precum 'La fiecare 30 de zile'.",
    },
    "ends": {"en": "Ends", "ro": "Se termină"},
    "recurrence_updated": {"en": "Recurrence updated", "ro": "Recurență actualizată"},
    "recurrence_disabled": {
        "en": "Recurrence disabled",
        "ro": "Recurență dezactivată",
    },
    "recurrence_day_mon": {"en": "Mo", "ro": "Lu"},
    "recurrence_day_tue": {"en": "Tu", "ro": "Ma"},
    "recurrence_day_wed": {"en": "We", "ro": "Mi"},
    "recurrence_day_thu": {"en": "Th", "ro": "Jo"},
    "recurrence_day_fri": {"en": "Fr", "ro": "Vi"},
    "recurrence_day_sat": {"en": "Sa", "ro": "Sâ"},
    "recurrence_day_sun": {"en": "Su", "ro": "Du"},

    # Task dialogs - Stats
    "time_spent": {"en": "Time spent", "ro": "Timp petrecut"},
    "remaining": {"en": "Remaining", "ro": "Rămas"},
    "progress": {"en": "Progress", "ro": "Progres"},
    "pct_complete": {"en": "{pct}% complete", "ro": "{pct}% finalizat"},
    "time_entries_label": {"en": "Time entries", "ro": "Înregistrări de timp"},
    "view_all_time_entries": {
        "en": "View all time entries",
        "ro": "Vezi toate înregistrările de timp",
    },
    "stats_title": {"en": "Stats: {title}", "ro": "Statistici: {title}"},
    "project_colon": {"en": "Project: {name}", "ro": "Proiect: {name}"},
    "one_time_entry": {"en": "1 time entry", "ro": "1 înregistrare de timp"},
    "n_time_entries": {
        "en": "{count} time entries",
        "ro": "{count} înregistrări de timp",
    },

    # Daily notes
    "daily_note_hint": {
        "en": "Write about your day... Markdown supported",
        "ro": "Scrie despre ziua ta... Markdown suportat",
    },
    "daily_note_saved": {"en": "Daily note saved", "ro": "Notița zilnică salvată"},
    "failed_to_save_note": {
        "en": "Failed to save note: {error}",
        "ro": "Nu s-a putut salva notița: {error}",
    },
    "how_was_your_day": {"en": "How was your day?", "ro": "Cum a fost ziua ta?"},
    "daily_note": {"en": "Daily note", "ro": "Notiță zilnică"},
    "no_note_yet": {"en": "No note yet", "ro": "Nicio notiță încă"},
    "recent_notes": {"en": "Recent notes", "ro": "Notițe recente"},
    "no_notes_yet": {"en": "No notes yet", "ro": "Nicio notiță încă"},
    "no_notes_yet_desc": {
        "en": "Your daily notes will appear here",
        "ro": "Notițele tale zilnice vor apărea aici",
    },
    "todays_note": {"en": "Today's note", "ro": "Notița de azi"},
    "tap_to_write": {"en": "Tap to write about your day", "ro": "Atinge pentru a scrie despre ziua ta"},
    "edit_in_notes": {"en": "Edit in notes", "ro": "Editează în notițe"},

    # Task dialogs - Delete recurrence
    "task_is_recurring": {
        "en": "'{title}' is a recurring task.",
        "ro": "'{title}' este o treabă recurentă.",
    },
    "delete_this_occurrence": {
        "en": "Delete this occurrence only",
        "ro": "Șterge doar această apariție",
    },
    "delete_occurrence_explanation": {
        "en": "Removes only this instance. Future occurrences will still "
              "be created when you complete tasks.",
        "ro": "Elimină doar această instanță. Aparițiile viitoare vor fi "
              "create în continuare când finalizezi treburi.",
    },
    "delete_all_occurrences": {
        "en": "Delete all occurrences",
        "ro": "Șterge toate aparițiile",
    },
    "delete_all_explanation": {
        "en": "Removes this task and all other pending/completed instances "
              "with the same recurrence.",
        "ro": "Elimină această treabă și toate celelalte instanțe "
              "în așteptare/finalizate cu aceeași recurență.",
    },
    "delete_recurring_task": {
        "en": "Delete recurring task",
        "ro": "Șterge treaba recurentă",
    },

    # Task details dialog (add details before submit)
    "due_date": {"en": "Due date", "ro": "Dată scadentă"},
    "custom_date": {"en": "Custom...", "ro": "Personalizat..."},
    "none_date": {"en": "None", "ro": "Fără"},

    # Task dialogs - Duration completion
    "how_long_spent": {
        "en": "How long did you spend on this task?",
        "ro": "Cât timp ai petrecut pe această treabă?",
    },
    "complete_title": {
        "en": "Complete: {title}",
        "ro": "Finalizează: {title}",
    },
    "skip": {"en": "Skip", "ro": "Sari"},
    "complete_action": {"en": "Complete", "ro": "Finalizează"},
    "drag_to_adjust": {"en": "drag to adjust", "ro": "trage pentru a ajusta"},

    # Claude chat
    "claude_chat": {"en": "Claude chat", "ro": "Chat Claude"},
    "ask_claude": {"en": "Ask Claude...", "ro": "Întreabă-l pe Claude..."},
    "claude_api_key": {"en": "Claude API key", "ro": "Cheie API Claude"},
    "api_key_setup_desc": {
        "en": "Enter your Anthropic API key to chat with Claude. Your key is stored securely on-device and never shared.",
        "ro": (
            "Introdu cheia ta API Anthropic pentru a discuta cu Claude. "
            "Cheia ta este stocată în siguranță pe dispozitiv și nu este partajată niciodată."
        ),
    },
    "api_key_saved": {"en": "API key saved", "ro": "Cheie API salvată"},
    "api_key_required": {"en": "API key required", "ro": "Cheie API necesară"},
    "chat_error": {"en": "Chat error", "ro": "Eroare chat"},
    "invalid_api_key": {
        "en": "Invalid API key. Check your key in settings.",
        "ro": "Cheie API invalidă. Verifică cheia în setări.",
    },
    "change_api_key": {"en": "Change API key", "ro": "Schimbă cheia API"},
    "task_created_chat": {"en": "Created", "ro": "Creat"},
    "task_completed_chat": {"en": "Completed", "ro": "Finalizat"},
    "task_deleted_chat": {"en": "Deleted", "ro": "Șters"},
    "task_renamed_chat": {"en": "Renamed", "ro": "Redenumit"},
    "task_postponed_chat": {"en": "Postponed", "ro": "Amânat"},
    "recurrence_set_chat": {"en": "Recurrence set", "ro": "Recurență setată"},
    "time_logged_chat": {"en": "Time logged", "ro": "Timp înregistrat"},
    "draft_created_chat": {"en": "Draft created", "ro": "Ciornă creată"},
    "draft_published_chat": {"en": "Draft published", "ro": "Ciornă publicată"},
    "project_created_chat": {"en": "Project created", "ro": "Proiect creat"},
    "send": {"en": "Send", "ro": "Trimite"},
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
