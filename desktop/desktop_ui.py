"""The desktop shell: responsive preview and focused, compact settings tabs."""
import tkinter as tk
from tkinter import ttk
from model import ACTION_NAMES
from media import source_label
import startup
import theme

IDLE_CHOICES = {"30 saniye": 30, "1 dakika": 60, "2 dakika": 120, "5 dakika": 300, "Kapalı": 0}


def label(parent, text, size=10, bold=False, muted=False, **kwargs):
    return ttk.Label(parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"),
                     foreground=theme.MUTED if muted else theme.FG, **kwargs)


def section(parent, title, detail=None):
    box = ttk.Frame(parent)
    box.pack(fill="x", pady=(0, 17))
    label(box, title, 11, True).pack(anchor="w", pady=(0, 7))
    if detail:
        label(box, detail, 9, muted=True, wraplength=310).pack(anchor="w", pady=(0, 8))
    return box


class ScrollableTab(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,bg=theme.BG,highlightthickness=0,width=310,height=1)
        self.bar=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview,style='Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=self.scrollbar_changed)
        self.canvas.pack(side='left',fill='both',expand=True)
        self.content=ttk.Frame(self.canvas,padding=15)
        self.item=self.canvas.create_window((0,0),window=self.content,anchor='nw')
        self.content.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(self.item,width=event.width))
        self.bind_all('<MouseWheel>',self.wheel,add='+')
    def scrollbar_changed(self,low,high):
        if float(low)<=0 and float(high)>=1:
            if self.bar.winfo_ismapped():self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():self.bar.pack(side='right',fill='y')
        self.bar.set(low,high)
    def wheel(self,event):
        path=str(event.widget);prefix=str(self)
        if (path==prefix or path.startswith(prefix+'.')) and '.popdown' not in path and getattr(event.widget,'winfo_class',lambda:'')() not in ('TCombobox','TSpinbox'):
            if self.canvas.yview()!=(0.0,1.0):self.canvas.yview_scroll(-int(event.delta/120),'units')
            return 'break'


def build_ui(app):
    root = app.root
    root.title("MacroDeck · Medya")
    root.configure(bg=theme.BG)
    width = min(1160, max(940, root.winfo_screenwidth() - 120))
    height = min(800, max(640, root.winfo_screenheight() - 100))
    root.geometry(f"{width}x{height}")
    root.minsize(940, 640)
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=theme.BG, foreground=theme.FG)
    style.configure("TFrame", background=theme.BG)
    style.configure("TLabel", background=theme.BG, foreground=theme.FG)
    style.configure("TCheckbutton", background=theme.BG, foreground=theme.FG)
    style.map("TCheckbutton", background=[("active", theme.BG)])
    style.configure("TButton", background=theme.SURFACE, foreground=theme.FG, padding=(12, 9), borderwidth=0)
    style.map("TButton", background=[("pressed", theme.BERRY), ("active", theme.SURFACE_HOVER)], foreground=[("disabled", theme.MUTED)])
    style.configure("Accent.TButton", background=theme.SALMON, foreground=theme.INK)
    style.map("Accent.TButton", background=[("pressed", theme.ROSE), ("active", theme.CORAL)], foreground=[("disabled", theme.MUTED)])
    style.configure("TCombobox", fieldbackground=theme.SURFACE, background=theme.SURFACE,
                    foreground=theme.FG, arrowcolor=theme.CORAL, padding=7)
    style.map("TCombobox", fieldbackground=[("readonly", theme.SURFACE)], foreground=[("readonly", theme.FG)])
    style.configure("TSpinbox", fieldbackground=theme.SURFACE, foreground=theme.FG, arrowcolor=theme.CORAL, padding=5)
    style.configure("TNotebook", background=theme.BG, borderwidth=0,lightcolor=theme.BG,darkcolor=theme.BG,bordercolor=theme.BG)
    style.configure("TCombobox",bordercolor=theme.SURFACE,lightcolor=theme.SURFACE,darkcolor=theme.SURFACE)
    style.configure("TSpinbox",bordercolor=theme.SURFACE,lightcolor=theme.SURFACE,darkcolor=theme.SURFACE)
    style.configure("TScale",bordercolor=theme.SURFACE,lightcolor=theme.SURFACE,darkcolor=theme.SURFACE)
    style.configure("Vertical.TScrollbar",background=theme.SURFACE_HOVER,troughcolor=theme.BG,arrowcolor=theme.MUTED,bordercolor=theme.BG,lightcolor=theme.SURFACE_HOVER,darkcolor=theme.SURFACE_HOVER,arrowsize=10)
    style.configure("Brightness.Horizontal.TScale",background=theme.CORAL,troughcolor=theme.SURFACE,bordercolor=theme.CORAL,lightcolor=theme.CORAL,darkcolor=theme.CORAL,sliderlength=18)
    style.map("Brightness.Horizontal.TScale",background=[('active',theme.SALMON)])
    style.configure("TNotebook.Tab", background=theme.SURFACE, foreground=theme.MUTED, padding=(14, 10),borderwidth=0,lightcolor=theme.BG,darkcolor=theme.BG,bordercolor=theme.BG)
    style.map("TNotebook.Tab", background=[("selected", theme.SURFACE_HOVER)], foreground=[("selected", theme.FG)])
    style.configure("Horizontal.TScale", background=theme.BG, troughcolor=theme.SURFACE)
    root.option_add("*TCombobox*Listbox.background", theme.SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", theme.FG)
    root.option_add("*TCombobox*Listbox.selectBackground", theme.BERRY)

    shell = ttk.Frame(root, padding=22)
    shell.pack(fill="both", expand=True)
    header = ttk.Frame(shell)
    header.pack(fill="x", pady=(0, 18))
    brand = ttk.Frame(header)
    brand.pack(side="left")
    label(brand, "MacroDeck", 23, True).pack(anchor="w")
    label(brand, "Müziğin ve videoların, elinin altında.", 10, muted=True).pack(anchor="w")
    app.hide_button=ttk.Button(header,text='Simgeye gizle',command=app.hide_window)
    app.hide_button.pack(side='right',anchor='n',padx=(16,0),pady=2)
    app.connection_label = tk.StringVar(value="●  Cihaz aranıyor")
    ttk.Label(header, textvariable=app.connection_label, foreground=theme.CORAL, font=("Segoe UI", 11, "bold")).pack(side="right", anchor="n", pady=9)
    body = ttk.Frame(shell)
    body.pack(fill="both", expand=True)
    body.columnconfigure(0, weight=1)
    body.columnconfigure(1, weight=0)
    body.rowconfigure(0, weight=1)
    left = ttk.Frame(body)
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
    left.columnconfigure(0, weight=1)
    left.rowconfigure(1, weight=1)
    title_row = ttk.Frame(left)
    title_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    label(title_row, "CİHAZ EKRANI", 9, True, muted=True).pack(side="left")
    label(title_row, "Önizlemeye tıklayarak da kullanabilirsin", 9, muted=True).pack(side="right")
    app.preview_host = tk.Frame(left, bg=theme.SURFACE, highlightbackground=theme.SURFACE_HOVER, highlightthickness=1)
    app.preview_host.grid(row=1, column=0, sticky="nsew")
    app.preview = tk.Label(app.preview_host, bg=theme.SURFACE, bd=0, cursor="hand2")
    app.preview.place(relx=0.5, rely=0.5, anchor="center")
    app.preview.bind("<ButtonPress-1>", lambda event: app.preview_pointer(event, "down"))
    app.preview.bind("<B1-Motion>", lambda event: app.preview_pointer(event, "move"))
    app.preview.bind("<ButtonRelease-1>", lambda event: app.preview_pointer(event, "up"))
    app.preview_host.bind("<Configure>", app.resize_preview)
    app.track_title = tk.StringVar(value="Medya bekleniyor")
    app.track_artist = tk.StringVar(value="Apple Music, Spotify veya tarayıcıda bir içerik aç.")
    title_label=ttk.Label(left, textvariable=app.track_title, font=("Segoe UI", 13, "bold"), wraplength=640)
    title_label.grid(row=2, column=0, sticky="w", pady=(15, 4))
    artist_label=ttk.Label(left, textvariable=app.track_artist, foreground=theme.MUTED, wraplength=640)
    artist_label.grid(row=3, column=0, sticky="w")
    hint = "Encoder: çevir → ses · 1 bas → oynat/duraklat · 2 bas → ileri · 3 bas → geri\nBasılı tut → sessize al/aç · Ekranda saat/dişli → parlaklık"
    hint_label=label(left, hint, 9, muted=True, wraplength=640)
    hint_label.grid(row=4, column=0, sticky="w", pady=(15, 0))
    def resize_details(event):
        width=max(200,event.width)
        if width==getattr(left,'_detail_width',None):return
        left._detail_width=width
        for widget in (title_label,artist_label,hint_label):widget.configure(wraplength=width)
    left.bind('<Configure>',resize_details)

    tabs = ttk.Notebook(body, width=340)
    tabs.grid(row=0, column=1, sticky="nsew")
    control_tab=ScrollableTab(tabs);control=control_tab.content
    keys_tab=ScrollableTab(tabs);keys=keys_tab.content
    connection_tab=ScrollableTab(tabs);connection=connection_tab.content
    tabs.add(control_tab,text='Kontrol')
    tabs.add(keys_tab,text='Tuşlar')
    tabs.add(connection_tab,text='Bağlantı')

    source = section(control, "Medya kaynağı", "Otomatik mod çalan uygulamayı takip eder. Bir kaynak seçersen ona bağlı kalır.")
    app.source_combo = ttk.Combobox(source, state="readonly", values=["Otomatik"])
    app.source_combo.pack(fill="x")
    app.source_combo.current(0)
    app.source_combo.bind("<<ComboboxSelected>>", app.choose_source)
    app.source_ids = [None]
    app.media_buttons = {}
    media_row = ttk.Frame(source)
    media_row.pack(fill="x", pady=(9, 0))
    for text, action in (("Önceki", "previous"), ("Oynat", "play_pause"), ("Sonraki", "next")):
        button = ttk.Button(media_row, text=text, command=lambda action=action: app.commands.put(("media", action)))
        button.pack(side="left", expand=True, fill="x", padx=(0, 3))
        app.media_buttons[action] = button

    brightness = section(control, "Ekran parlaklığı")
    app.brightness_var = tk.DoubleVar(value=app.brightness_initial)
    app.brightness_label = tk.StringVar(value=f"%{app.brightness_initial}")
    row = ttk.Frame(brightness)
    row.pack(fill="x")
    ttk.Scale(row, from_=5, to=100, variable=app.brightness_var, command=app.brightness_changed,style="Brightness.Horizontal.TScale").pack(side="left", fill="x", expand=True)
    ttk.Label(row, textvariable=app.brightness_label, width=5).pack(side="right", padx=(12, 0))
    presets = ttk.Frame(brightness)
    presets.pack(fill="x", pady=(7, 0))
    for value in (25, 50, 100):
        ttk.Button(presets, text=f"%{value}", command=lambda value=value: app.queue_brightness(value)).pack(side="left", fill="x", expand=True, padx=(0, 4))
    app.volume_label = tk.StringVar(value="Ses bilgisi bekleniyor")
    ttk.Label(brightness, textvariable=app.volume_label, foreground=theme.MUTED).pack(anchor="w", pady=(8, 0))
    app.output_label=tk.StringVar(value='Ses çıkışı okunuyor')
    ttk.Label(brightness,textvariable=app.output_label,foreground=theme.MUTED,wraplength=310).pack(anchor='w',pady=(4,0))

    display = section(control, "Bekleme ekranı")
    app.idle_var = tk.StringVar(value=next(name for name, value in IDLE_CHOICES.items() if value == app.ui_settings.idle_seconds))
    row = ttk.Frame(display)
    row.pack(fill="x")
    label(row, "Bekleme süresi", 9, muted=True).pack(side="left")
    ttk.Combobox(row, textvariable=app.idle_var, values=list(IDLE_CHOICES), state="readonly", width=13).pack(side="right")
    app.dim_enabled_var = tk.BooleanVar(value=app.ui_settings.dim_enabled)
    app.dim_percent_var = tk.IntVar(value=app.ui_settings.dim_percent)
    ttk.Checkbutton(display, text="Beklerken ekran ışığını kıs", variable=app.dim_enabled_var).pack(anchor="w", pady=(8, 4))
    row = ttk.Frame(display)
    row.pack(fill="x")
    label(row, "Bekleme parlaklığı (%)", 9, muted=True).pack(side="left")
    ttk.Spinbox(row, from_=5, to=50, textvariable=app.dim_percent_var, width=5).pack(side="right")
    ttk.Button(display, text="Ekran ayarlarını uygula", command=app.save_display_preferences).pack(fill="x", pady=(9, 0))

    label(keys, "Fiziksel tuşlar", 12, True).pack(anchor="w", pady=(0, 5))
    label(keys, "Atamalar kartın belleğine kaydedilir.", 9, muted=True).pack(anchor="w", pady=(0, 13))
    grid = ttk.Frame(keys)
    grid.pack(fill="x")
    grid.columnconfigure(1, weight=1)
    app.key_vars = []
    for index, action in enumerate(app.config["keys"]):
        variable = tk.StringVar(value=ACTION_NAMES[action])
        app.key_vars.append(variable)
        label(grid, f"Tuş {index+1}", 10).grid(row=index, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Combobox(grid, textvariable=variable, values=ACTION_NAMES, state="readonly", width=23).grid(row=index, column=1, sticky="ew", pady=5)
    app.invert = tk.BooleanVar(value=app.config["invert"])
    app.steps = tk.StringVar(value=str(app.config["steps"]))
    ttk.Checkbutton(keys, text="Encoder yönünü ters çevir", variable=app.invert).pack(anchor="w", pady=(20, 8))
    row = ttk.Frame(keys)
    row.pack(fill="x")
    label(row, "Encoder adımı", 9, muted=True).pack(side="left")
    ttk.Combobox(row, textvariable=app.steps, values=["2", "4"], state="readonly", width=5).pack(side="right")
    ttk.Button(keys, text="Tuş ayarlarını kaydet", style="Accent.TButton", command=app.save).pack(fill="x", pady=(18, 0))
    label(keys, "Discord için F13/F14 gibi tuşları Discord’un kısayol ayarlarında mikrofon ve sağırlaştırma işlevlerine atayabilirsin.", 9, muted=True, wraplength=310).pack(anchor="w", pady=(14, 0))

    usb = section(connection, "Cihaz bağlantısı", "Kart otomatik bulunur. Gerekirse bağlantıyı buradan elle seçebilirsin.")
    app.port = tk.StringVar(value=app.args.port or "")
    row = ttk.Frame(usb)
    row.pack(fill="x")
    app.port_box = ttk.Combobox(row, textvariable=app.port, width=12, state="readonly")
    app.port_box.pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="Yenile", command=app.refresh_ports).pack(side="right", padx=(6, 0))
    row = ttk.Frame(usb)
    row.pack(fill="x", pady=(8, 0))
    ttk.Button(row, text="Bağlan", style="Accent.TButton", command=app.connect).pack(side="left", expand=True, fill="x", padx=(0, 4))
    ttk.Button(row, text="Otomatik", command=app.auto_connect).pack(side="left", expand=True, fill="x")
    ttk.Button(usb, text="Bağlantıyı kes", command=lambda: app.commands.put(("disconnect", None))).pack(fill="x", pady=(6, 0))
    app.device_label = tk.StringVar(value="Cihaz bekleniyor")
    app.transfer_label = tk.StringVar(value="Henüz ekran aktarımı yok")
    ttk.Label(usb, textvariable=app.device_label, foreground=theme.MUTED, wraplength=310).pack(anchor="w", pady=(10, 3))
    ttk.Label(usb, textvariable=app.transfer_label, foreground=theme.MUTED, wraplength=310).pack(anchor="w")
    calibration = section(connection, "Dokunmatik", "Dokunuşlar kayıksa dört noktalı kalibrasyonu yeniden yapabilirsin.")
    ttk.Button(calibration, text="Dokunmatiği ayarla", command=lambda: app.commands.put(("calibrate", None))).pack(fill="x")
    ttk.Button(calibration, text="Kalibrasyonu iptal et", command=lambda: app.commands.put(("cancel_calibration", None))).pack(fill="x", pady=(5, 0))
    startup_box = section(connection, "Başlangıç")
    app.autostart = tk.BooleanVar(value=startup.enabled())
    ttk.Checkbutton(startup_box, text="Windows açılınca başlat", variable=app.autostart, command=app.toggle_startup).pack(anchor="w")
    app.demo = tk.BooleanVar(value=app.args.demo)
    ttk.Checkbutton(startup_box, text="Demo önizlemesi · kontroller pasif", variable=app.demo, command=lambda: app.commands.put(("demo", app.demo.get()))).pack(anchor="w", pady=(7, 0))
    diagnostics=section(connection,'Tanılama','Bağlantı ve performans bilgilerini dosyaya kaydeder. Medya başlığı veya kişisel içerik eklenmez.')
    ttk.Button(diagnostics,text='Tanılama raporunu kaydet',command=app.save_report).pack(fill='x')
    footer = ttk.Frame(shell)
    footer.pack(fill="x", pady=(16, 0))
    ttk.Label(footer, textvariable=app.status, foreground=theme.MUTED, wraplength=1000).pack(anchor="w")
