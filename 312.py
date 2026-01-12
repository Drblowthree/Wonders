#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═════════════════════════════════════════════════════════════════════════════════════╗
║                    W O L F P A C K   M I S S I O N   C O N T R O L                  ║
║                              Version 9.1.0 | Build 2024                             ║
╠═════════════════════════════════════════════════════════════════════════════════════╣
║  SEQUENCE:                                                                          ║
║  1. CHARGE    - Hold left click                                                     ║
║  2. CANCEL    - Right click + release left (together, fast!)                        ║
║  3. DISCONNECT - Network cut immediately                                            ║
║  4. INVENTORY - Open, drag item, close                                              ║
║  5. COMBAT    - Left click spam + RECONNECT on click #N                             ║
║  6. PICKUP    - E-spam to pick item back up                                         ║
║  7. LOOP                                                                            ║
╚═════════════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import sys
import time
import json
import ctypes
import ctypes.wintypes
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, Tuple
from datetime import datetime
from pathlib import Path
from enum import Enum
import atexit

# ══════════════════════════════════════════════════════════════════════════════════════
# SYSTEM INITIALIZATION
# ══════════════════════════════════════════════════════════════════════════════════════

VERSION = "9.6.0"
CODENAME = "APEX PREDATOR"

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

APP_DIR = Path(__file__).parent if not getattr(sys, 'frozen', False) else Path(sys.executable).parent
CONFIG_DIR = APP_DIR / "mission_data"
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"

# ══════════════════════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ══════════════════════════════════════════════════════════════════════════════════════

try:
    import pygame
    pygame.init()
    pygame.joystick.init()
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

try:
    from pynput import keyboard, mouse
    from pynput.keyboard import Key, Controller as KBController
    from pynput.mouse import Button, Controller as MouseController
    PYNPUT_OK = True
except ImportError:
    PYNPUT_OK = False

try:
    import pydivert
    PYDIVERT_OK = True
except ImportError:
    PYDIVERT_OK = False

if not PYNPUT_OK:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("SYSTEM FAILURE", "Missing: pynput\n\nRun: pip install pynput")
    sys.exit(1)

user32 = ctypes.windll.user32


# ══════════════════════════════════════════════════════════════════════════════════════
# THEME
# ══════════════════════════════════════════════════════════════════════════════════════

class Theme:
    SPACE = "#030308"
    DEEP = "#05050a"
    PANEL = "#0a0a12"
    SURFACE = "#12121f"
    ELEVATED = "#181828"
    NOMINAL = "#00ff88"
    CAUTION = "#ffaa00"
    CRITICAL = "#ff3366"
    STANDBY = "#00aaff"
    OFFLINE = "#666688"
    PRIMARY = "#4d7cff"
    ACCENT = "#00e5ff"
    PHASE_CHARGE = "#00e5ff"
    PHASE_CANCEL = "#ffdd00"
    PHASE_NETWORK = "#ff3366"
    PHASE_INVENTORY = "#ff9100"
    PHASE_COMBAT = "#ff00aa"
    PHASE_PICKUP = "#00ff88"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#aaaacc"
    TEXT_DIM = "#666688"
    BORDER_DIM = "#1a1a2e"
    BORDER_NORMAL = "#2a2a44"


# ══════════════════════════════════════════════════════════════════════════════════════
# NETWORK CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════════════

class NetworkMode(Enum):
    PYDIVERT = "PyDivert"
    FIREWALL = "Firewall"


class NetworkController:
    def __init__(self, mode: NetworkMode = None, log_func: Callable = None):
        self._lock = threading.RLock()
        self._active = False
        self._handle = None
        self._log = log_func or print
        self._mode = mode or (NetworkMode.PYDIVERT if PYDIVERT_OK else NetworkMode.FIREWALL)
        
        self._si = subprocess.STARTUPINFO()
        self._si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self._si.wShowWindow = subprocess.SW_HIDE
    
    @property
    def mode(self) -> NetworkMode:
        return self._mode
    
    @mode.setter
    def mode(self, value: NetworkMode):
        if self._active:
            self.reconnect()
        self._mode = value
    
    def disconnect(self) -> bool:
        with self._lock:
            if self._active:
                return True
            if self._mode == NetworkMode.PYDIVERT:
                success = self._pydivert_block()
            else:
                success = self._firewall_block()
            if success:
                self._active = True
            return success
    
    def reconnect(self) -> bool:
        with self._lock:
            if not self._active:
                return True
            if self._mode == NetworkMode.PYDIVERT:
                success = self._pydivert_restore()
            else:
                success = self._firewall_restore()
            if success:
                self._active = False
            return success
    
    def cleanup(self):
        with self._lock:
            self._pydivert_restore()
            self._firewall_restore()
            self._active = False
    
    def _pydivert_block(self) -> bool:
        if not PYDIVERT_OK:
            return False
        try:
            self._handle = pydivert.WinDivert("outbound")
            self._handle.open()
            threading.Thread(target=self._consume, daemon=True).start()
            return True
        except Exception as e:
            self._log(f"PyDivert error: {e}")
            return False
    
    def _consume(self):
        while self._active and self._handle:
            try:
                self._handle.recv()
            except:
                break
    
    def _pydivert_restore(self) -> bool:
        try:
            if self._handle:
                self._handle.close()
                self._handle = None
            return True
        except:
            return False
    
    def _firewall_block(self) -> bool:
        self._run("netsh advfirewall set allprofiles state on")
        return self._run("netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound")
    
    def _firewall_restore(self) -> bool:
        return self._run("netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound", wait=True)
    
    def _run(self, cmd: str, wait: bool = False) -> bool:
        try:
            if wait:
                subprocess.run(cmd, shell=True, startupinfo=self._si, creationflags=subprocess.CREATE_NO_WINDOW, timeout=3)
            else:
                subprocess.Popen(cmd, shell=True, startupinfo=self._si, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except:
            return False


# ══════════════════════════════════════════════════════════════════════════════════════
# COORDINATE MAPPER
# ══════════════════════════════════════════════════════════════════════════════════════

class CoordinateMapper:
    BASE_W, BASE_H = 1920, 1080
    
    def __init__(self):
        self.left = self.top = 0
        self.width, self.height = self.BASE_W, self.BASE_H
    
    def calibrate(self, exclude_hwnd: int = 0) -> bool:
        try:
            pt = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            hwnd = user32.WindowFromPoint(pt)
            if hwnd:
                hwnd = user32.GetAncestor(hwnd, 2)
            if not hwnd or (exclude_hwnd and int(hwnd) == int(exclude_hwnd)):
                return False
            
            rect = ctypes.wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            scr = ctypes.wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(scr))
            
            self.left, self.top = scr.x, scr.y
            self.width = rect.right - rect.left
            self.height = rect.bottom - rect.top
            return self.width > 100 and self.height > 100
        except:
            return False
    
    def translate(self, x: int, y: int) -> Tuple[int, int]:
        return (
            int(self.left + x * self.width / self.BASE_W),
            int(self.top + y * self.height / self.BASE_H)
        )


# ══════════════════════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════════════

class TelemetrySlider(tk.Canvas):
    def __init__(self, parent, label, min_val, max_val, initial, unit="ms", on_change=None, **kwargs):
        super().__init__(parent, height=52, bg=Theme.PANEL, highlightthickness=0, **kwargs)
        self.label, self.min_val, self.max_val, self.unit = label, min_val, max_val, unit
        self.on_change = on_change
        self._value, self._active, self._hover = initial, False, False
        
        self.bind("<Configure>", lambda e: self._render())
        self.bind("<Button-1>", lambda e: self._update(e.x))
        self.bind("<B1-Motion>", lambda e: self._update(e.x))
        self.bind("<Enter>", lambda e: (setattr(self, '_hover', True), self._render()))
        self.bind("<Leave>", lambda e: (setattr(self, '_hover', False), self._render()))
    
    def _update(self, x):
        w = self.winfo_width()
        pad = 16
        ratio = max(0, min(1, (x - pad) / (w - pad * 2)))
        new_val = int(self.min_val + ratio * (self.max_val - self.min_val))
        if new_val != self._value:
            self._value = new_val
            self._render()
            if self.on_change:
                self.on_change(self._value)
    
    def set(self, value):
        self._value = max(self.min_val, min(self.max_val, value))
        self._render()
        if self.on_change:
            self.on_change(self._value)
    
    def get(self):
        return self._value
    
    def _render(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        pad = 16
        
        bg = Theme.SURFACE if self._hover else Theme.PANEL
        self.create_rectangle(0, 0, w, h, fill=bg, outline="")
        
        if self._active:
            self.create_rectangle(0, 0, 3, h, fill=Theme.NOMINAL, outline="")
        
        dot_color = Theme.NOMINAL if self._active else (Theme.STANDBY if self._hover else Theme.OFFLINE)
        self.create_oval(pad, 10, pad + 8, 18, fill=dot_color, outline="")
        
        label_color = Theme.TEXT_PRIMARY if self._active else Theme.TEXT_SECONDARY
        self.create_text(pad + 14, 14, text=self.label.upper(), anchor="w", fill=label_color, font=("Consolas", 9))
        
        val_color = Theme.ACCENT if self._hover else (Theme.NOMINAL if self._active else Theme.TEXT_PRIMARY)
        self.create_text(w - pad, 14, text=f"{self._value:,}{self.unit}", anchor="e", fill=val_color, font=("Consolas", 10, "bold"))
        
        ty, th = 36, 6
        tw = w - pad * 2
        ratio = (self._value - self.min_val) / max(1, self.max_val - self.min_val)
        
        self.create_rectangle(pad, ty, w - pad, ty + th, fill=Theme.DEEP, outline="")
        
        fill_w = tw * ratio
        if fill_w > 0:
            self.create_rectangle(pad, ty, pad + fill_w, ty + th, fill=(Theme.NOMINAL if self._active else Theme.PRIMARY), outline="")
        
        thumb_x = pad + fill_w
        thumb_r = 8 if self._hover else 6
        self.create_oval(thumb_x - thumb_r, ty + th/2 - thumb_r, thumb_x + thumb_r, ty + th/2 + thumb_r, fill=Theme.TEXT_PRIMARY, outline="")


class PhaseIndicator(tk.Canvas):
    def __init__(self, parent, label, color, **kwargs):
        super().__init__(parent, width=72, height=55, bg=Theme.SPACE, highlightthickness=0, **kwargs)
        self.label, self.color, self._active = label, color, False
        self._render()
    
    def set_active(self, active: bool):
        self._active = active
        self._render()
    
    def _render(self):
        self.delete("all")
        w, h = 72, 55
        frame_color = self.color if self._active else Theme.BORDER_DIM
        self.create_rectangle(2, 2, w-2, h-2, fill="", outline=frame_color, width=1)
        fill_color = self.color if self._active else Theme.PANEL
        self.create_rectangle(4, 4, w-4, h-4, fill=fill_color, outline="")
        light_color = Theme.TEXT_PRIMARY if self._active else Theme.OFFLINE
        self.create_oval(w/2 - 4, 10, w/2 + 4, 18, fill=light_color, outline="")
        text_color = Theme.SPACE if self._active else Theme.TEXT_DIM
        self.create_text(w/2, 38, text=self.label, fill=text_color, font=("Consolas", 7, "bold"))


class SystemStatus(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=70, bg=Theme.DEEP, highlightthickness=0, **kwargs)
        self._status, self._status_color = "STANDBY", Theme.STANDBY
        self._loop, self._net_mode, self._net_state = 0, "---", "OFFLINE"
        self.bind("<Configure>", lambda e: self._render())
    
    def set_status(self, status, color):
        self._status, self._status_color = status, color
        self._render()
    
    def set_loop(self, count):
        self._loop = count
        self._render()
    
    def set_network(self, mode, state):
        self._net_mode, self._net_state = mode, state
        self._render()
    
    def _render(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        self.create_rectangle(0, 0, w, h, fill=Theme.DEEP, outline="")
        for i in range(0, h, 4):
            self.create_line(0, i, w, i, fill=Theme.PANEL)
        self.create_rectangle(1, 1, w-1, h-1, fill="", outline=Theme.BORDER_NORMAL)
        
        self.create_text(15, 22, text="STATUS:", anchor="w", fill=Theme.TEXT_DIM, font=("Consolas", 9))
        self.create_text(75, 22, text=self._status, anchor="w", fill=self._status_color, font=("Consolas", 12, "bold"))
        
        self.create_text(15, 48, text="CYCLE:", anchor="w", fill=Theme.TEXT_DIM, font=("Consolas", 9))
        self.create_text(75, 48, text=f"{self._loop:,}", anchor="w", fill=Theme.ACCENT, font=("Consolas", 11, "bold"))
        
        net_color = Theme.NOMINAL if self._net_state == "ONLINE" else (Theme.CRITICAL if self._net_state == "BLOCKED" else Theme.OFFLINE)
        self.create_text(w - 15, 22, text=f"NET: {self._net_mode}", anchor="e", fill=Theme.TEXT_SECONDARY, font=("Consolas", 9))
        self.create_text(w - 15, 48, text=self._net_state, anchor="e", fill=net_color, font=("Consolas", 10, "bold"))


class TelemetryLog(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=Theme.DEEP, **kwargs)
        header = tk.Frame(self, bg=Theme.PANEL, height=22)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="▸ TELEMETRY", bg=Theme.PANEL, fg=Theme.TEXT_DIM, font=("Consolas", 8, "bold")).pack(side="left", padx=8, pady=3)
        self.text = tk.Text(self, bg=Theme.DEEP, fg=Theme.NOMINAL, font=("Consolas", 8), height=4, relief="flat", padx=8, pady=4)
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")
    
    def log(self, message, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        def _update():
            self.text.configure(state="normal")
            self.text.insert("end", f"[{ts}] {message}\n")
            self.text.see("end")
            self.text.configure(state="disabled")
        self.after(0, _update)


# ══════════════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════════════

class WolfpackApp:
    def __init__(self):
        self.running = False
        self.paused = False
        self._lock = threading.Lock()
        self.loop_count = 0
        
        self.KEY_MAP = {
            "F1": Key.f1, "F2": Key.f2, "F3": Key.f3, "F4": Key.f4, "F5": Key.f5, "F6": Key.f6,
            "F7": Key.f7, "F8": Key.f8, "F9": Key.f9, "F10": Key.f10, "F11": Key.f11, "F12": Key.f12,
            "HOME": Key.home, "END": Key.end, "INSERT": Key.insert, "DELETE": Key.delete,
            "PAGEUP": Key.page_up, "PAGEDOWN": Key.page_down,
        }
        
        self._load_config()
        
        self.root = tk.Tk()
        self.root.title(f"WOLFPACK v{VERSION}")
        self.root.geometry("560x600")
        self.root.configure(bg=Theme.SPACE)
        self.root.resizable(True, True)
        self.root.minsize(500, 500)
        self.root.attributes("-topmost", True)
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground=Theme.DEEP, background=Theme.ELEVATED, foreground=Theme.TEXT_PRIMARY)
        
        self.network = NetworkController(
            mode=NetworkMode.PYDIVERT if self.cfg["network_mode"] == "pydivert" else NetworkMode.FIREWALL,
            log_func=self._log
        )
        self.kb = KBController()
        self.ms = MouseController()
        self.mapper = CoordinateMapper()
        
        self.sliders = {}
        self.phases = {}
        
        self._build_ui()
        
        keyboard.Listener(on_press=self._on_hotkey).start()
        
        if not ctypes.windll.shell32.IsUserAnAdmin():
            messagebox.showwarning("Warning", "Run as Administrator for network control!")
        
        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)
        atexit.register(self.network.cleanup)
        
        self._log(f"Wolfpack v{VERSION} initialized")
        self._log(f"Network: {self.network.mode.value}")
        
        # Start controller if enabled
        if self.cfg["controller_enabled"] and PYGAME_OK:
            self._start_controller_thread()
    
    def _load_config(self):
        self.cfg = {
            "key_start": "F6", "key_pause": "F8", "key_stop": "F12",
            "network_mode": "pydivert" if PYDIVERT_OK else "firewall",
            "loop_enabled": True,
            "ping_offset": 0,  # Add/subtract from critical timings based on your ping
            "controller_enabled": False,
            "controller_start": "A",
            "controller_stop": "B",
            "controller_faster": "DPAD_LEFT",
            "controller_slower": "DPAD_RIGHT",
            # Phase 1: Charge
            "charge_hold": 150,
            # Phase 2: Cancel
            "cancel_hold": 50,
            "post_cancel_delay": 30,
            # Phase 3: Disconnect - FAST!
            "dc_delay": 0,
            "dc_settle": 50,
            # Phase 4: Inventory
            "inv_open": 400,
            "inv_settle": 150,
            "inv_grip": 100,
            "inv_drag": 600,
            "inv_drop": 100,
            "inv_close": 200,
            # Phase 5: Throw + Reconnect
            "throw_count": 2,
            "throw_hold": 49,
            "throw_delay": 49,
            "reconnect_on_throw": 1,
            "reconnect_delay": 25,
            # Phase 6: Pickup
            "e_count": 10,
            "e_hold": 20,
            "e_delay": 20,
            # Loop
            "loop_delay": 800,
        }
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    self.cfg.update(json.load(f))
        except:
            pass
    
    def _save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.cfg, f, indent=2)
            self._log("Config saved")
        except Exception as e:
            self._log(f"Save error: {e}")
    
    def _build_ui(self):
        # Header (always visible)
        header = tk.Frame(self.root, bg=Theme.SPACE, height=60)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="◆ WOLFPACK ◆", bg=Theme.SPACE, fg=Theme.PRIMARY, font=("Impact", 22)).pack(pady=(6, 0))
        
        # Phases (always visible)
        phase_frame = tk.Frame(self.root, bg=Theme.SPACE)
        phase_frame.pack(pady=4)
        phase_row = tk.Frame(phase_frame, bg=Theme.SPACE)
        phase_row.pack()
        
        for label, color, key in [
            ("CHARGE", Theme.PHASE_CHARGE, "charge"),
            ("CANCEL", Theme.PHASE_CANCEL, "cancel"),
            ("NET", Theme.PHASE_NETWORK, "network"),
            ("INV", Theme.PHASE_INVENTORY, "inventory"),
            ("THROW", Theme.PHASE_COMBAT, "combat"),
            ("PICKUP", Theme.PHASE_PICKUP, "pickup"),
        ]:
            ind = PhaseIndicator(phase_row, label, color)
            ind.pack(side="left", padx=2)
            self.phases[key] = ind
        
        # Tabs
        style = ttk.Style()
        style.configure('TNotebook', background=Theme.SPACE, borderwidth=0)
        style.configure('TNotebook.Tab', background=Theme.PANEL, foreground=Theme.TEXT_PRIMARY, 
                        padding=[12, 6], font=("Consolas", 9, "bold"))
        style.map('TNotebook.Tab', background=[('selected', Theme.ELEVATED)], 
                  foreground=[('selected', Theme.ACCENT)])
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=4)
        
        # === TAB 1: CONTROL ===
        tab_ctrl = tk.Frame(notebook, bg=Theme.SPACE)
        notebook.add(tab_ctrl, text=" ⚡ CONTROL ")
        
        # Timing Quick Adjust
        timing_frame = tk.Frame(tab_ctrl, bg=Theme.ELEVATED, pady=8)
        timing_frame.pack(fill="x", padx=8, pady=8)
        tk.Label(timing_frame, text="◂ NETWORK COMPENSATION ▸", bg=Theme.ELEVATED, fg=Theme.ACCENT, font=("Consolas", 9, "bold")).pack()
        tk.Label(timing_frame, text="High ping/lag? → SLOWER | Low ping? → FASTER", bg=Theme.ELEVATED, fg=Theme.TEXT_DIM, font=("Consolas", 8)).pack()
        
        self.ping_slider = TelemetrySlider(timing_frame, "Lag Offset", 0, 300, self.cfg.get("ping_offset", 0), unit="ms", on_change=self._on_ping_change)
        self.ping_slider.pack(fill="x", padx=8, pady=4)
        
        quick_row = tk.Frame(timing_frame, bg=Theme.ELEVATED)
        quick_row.pack(pady=4)
        tk.Button(quick_row, text="◀ -5", bg=Theme.PANEL, fg=Theme.TEXT_PRIMARY, font=("Consolas", 9), relief="flat", command=lambda: self._adjust_timing(-5)).pack(side="left", padx=4)
        tk.Button(quick_row, text="RESET", bg=Theme.PANEL, fg=Theme.CAUTION, font=("Consolas", 9), relief="flat", command=lambda: self._adjust_timing(0, reset=True)).pack(side="left", padx=4)
        tk.Button(quick_row, text="+5 ▶", bg=Theme.PANEL, fg=Theme.TEXT_PRIMARY, font=("Consolas", 9), relief="flat", command=lambda: self._adjust_timing(5)).pack(side="left", padx=4)
        
        # Status
        self.status = SystemStatus(tab_ctrl)
        self.status.pack(fill="x", padx=8, pady=8)
        self.status.set_network(self.network.mode.value, "ONLINE")
        
        # Log
        self.log_panel = TelemetryLog(tab_ctrl, height=100)
        self.log_panel.pack(fill="x", padx=8, pady=4)
        
        # Buttons
        btn_frame = tk.Frame(tab_ctrl, bg=Theme.SPACE)
        btn_frame.pack(fill="x", padx=8, pady=8)
        
        self.launch_btn = tk.Button(btn_frame, text=f"◆ LAUNCH [{self.cfg['key_start']}]", bg=Theme.NOMINAL, fg=Theme.SPACE, font=("Consolas", 11, "bold"), relief="flat", cursor="hand2", width=15, height=2, command=self._launch)
        self.launch_btn.pack(side="left", padx=2)
        
        self.pause_btn = tk.Button(btn_frame, text=f"❚❚ PAUSE [{self.cfg['key_pause']}]", bg=Theme.CAUTION, fg=Theme.SPACE, font=("Consolas", 11, "bold"), relief="flat", cursor="hand2", width=15, height=2, command=self._toggle_pause)
        self.pause_btn.pack(side="left", padx=2)
        
        self.abort_btn = tk.Button(btn_frame, text=f"■ ABORT [{self.cfg['key_stop']}]", bg=Theme.CRITICAL, fg=Theme.TEXT_PRIMARY, font=("Consolas", 11, "bold"), relief="flat", cursor="hand2", width=15, height=2, command=self._abort)
        self.abort_btn.pack(side="left", padx=2)
        
        # === TAB 2: TIMING ===
        tab_timing = tk.Frame(notebook, bg=Theme.SPACE)
        notebook.add(tab_timing, text=" ⏱ TIMING ")
        
        # Scrollable params
        canvas = tk.Canvas(tab_timing, bg=Theme.SPACE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab_timing, orient="vertical", command=canvas.yview)
        self.params_frame = tk.Frame(canvas, bg=Theme.SPACE)
        
        self.params_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.params_frame, anchor="nw", width=520)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        
        # Phase sliders
        self._section("PHASE 1: CHARGE", Theme.PHASE_CHARGE)
        self._slider("charge_hold", "Hold Duration", 10, 300)
        
        self._section("PHASE 2: CANCEL", Theme.PHASE_CANCEL)
        self._slider("cancel_hold", "Right Click Duration", 10, 200)
        self._slider("post_cancel_delay", "Post-Cancel Delay", 0, 200)
        
        self._section("PHASE 3: DISCONNECT", Theme.PHASE_NETWORK)
        self._slider("dc_delay", "Pre-Disconnect Delay", 0, 200)
        self._slider("dc_settle", "Settle Time", 0, 500)
        
        self._section("PHASE 4: INVENTORY", Theme.PHASE_INVENTORY)
        self._slider("inv_open", "Open Delay", 50, 800)
        self._slider("inv_settle", "Mouse Settle", 0, 300)
        self._slider("inv_grip", "Grip Time", 20, 500)
        self._slider("inv_drag", "Drag Duration", 100, 1500)
        self._slider("inv_drop", "Drop Delay", 20, 500)
        self._slider("inv_close", "Close Delay", 50, 500)
        
        self._section("PHASE 5: THROW + RECONNECT", Theme.PHASE_COMBAT)
        self._slider("throw_count", "Throw Count", 1, 10, unit="x")
        self._slider("throw_hold", "Throw Hold", 10, 200)
        self._slider("throw_delay", "Throw Interval", 10, 200)
        self._slider("reconnect_on_throw", "Reconnect On Throw #", 1, 10, unit="")
        self._slider("reconnect_delay", "Reconnect Delay", 0, 200)
        
        self._section("PHASE 6: PICKUP", Theme.PHASE_PICKUP)
        self._slider("e_count", "E-Press Count", 1, 50, unit="x")
        self._slider("e_hold", "E-Hold Time", 5, 100)
        self._slider("e_delay", "E-Interval", 5, 100)
        
        self._section("LOOP", Theme.TEXT_DIM)
        self._slider("loop_delay", "Cycle Delay", 0, 3000)
        
        # === TAB 3: SETTINGS ===
        tab_settings = tk.Frame(notebook, bg=Theme.SPACE)
        notebook.add(tab_settings, text=" ⚙ SETTINGS ")
        
        # Network
        net_frame = tk.Frame(tab_settings, bg=Theme.PANEL, pady=8)
        net_frame.pack(fill="x", padx=8, pady=8)
        tk.Label(net_frame, text="◂ NETWORK MODE ▸", bg=Theme.PANEL, fg=Theme.TEXT_DIM, font=("Consolas", 8)).pack()
        
        mode_row = tk.Frame(net_frame, bg=Theme.PANEL)
        mode_row.pack(pady=4)
        self.net_mode_var = tk.StringVar(value=self.cfg["network_mode"])
        
        for text, val, available, tag in [("PyDivert", "pydivert", PYDIVERT_OK, "[INSTANT]" if PYDIVERT_OK else "[N/A]"), ("Firewall", "firewall", True, "[FALLBACK]")]:
            fr = tk.Frame(mode_row, bg=Theme.PANEL)
            fr.pack(side="left", padx=15)
            tk.Radiobutton(fr, text=text, variable=self.net_mode_var, value=val, bg=Theme.PANEL, fg=Theme.TEXT_PRIMARY, selectcolor=Theme.DEEP, activebackground=Theme.PANEL, activeforeground=Theme.TEXT_PRIMARY, font=("Consolas", 10), state="normal" if available else "disabled", command=self._on_net_mode_change).pack(side="left")
            color = Theme.NOMINAL if (val == "pydivert" and PYDIVERT_OK) else Theme.CAUTION
            tk.Label(fr, text=tag, bg=Theme.PANEL, fg=color if available else Theme.OFFLINE, font=("Consolas", 8)).pack(side="left", padx=4)
        
        # Keybinds
        kb_frame = tk.Frame(tab_settings, bg=Theme.PANEL, pady=8)
        kb_frame.pack(fill="x", padx=8, pady=4)
        tk.Label(kb_frame, text="◂ KEYBINDS ▸", bg=Theme.PANEL, fg=Theme.TEXT_DIM, font=("Consolas", 8)).pack()
        
        keys_row = tk.Frame(kb_frame, bg=Theme.PANEL)
        keys_row.pack(pady=4)
        key_opts = list(self.KEY_MAP.keys())
        
        for label, cfg_key, color in [("START:", "key_start", Theme.NOMINAL), ("PAUSE:", "key_pause", Theme.CAUTION), ("STOP:", "key_stop", Theme.CRITICAL)]:
            fr = tk.Frame(keys_row, bg=Theme.PANEL)
            fr.pack(side="left", padx=8)
            tk.Label(fr, text=label, bg=Theme.PANEL, fg=color, font=("Consolas", 9, "bold")).pack(side="left")
            var = tk.StringVar(value=self.cfg[cfg_key])
            cb = ttk.Combobox(fr, textvariable=var, values=key_opts, width=6, state="readonly")
            cb.pack(side="left", padx=4)
            cb.bind("<<ComboboxSelected>>", lambda e, k=cfg_key, v=var: self._on_keybind_change(k, v.get()))
            setattr(self, f"{cfg_key}_var", var)
        
        # Loop Toggle
        loop_frame = tk.Frame(tab_settings, bg=Theme.PANEL, pady=8)
        loop_frame.pack(fill="x", padx=8, pady=4)
        self.loop_var = tk.BooleanVar(value=self.cfg["loop_enabled"])
        tk.Checkbutton(loop_frame, text="Enable Loop (repeat cycle)", variable=self.loop_var, bg=Theme.PANEL, fg=Theme.TEXT_PRIMARY, selectcolor=Theme.DEEP, activebackground=Theme.PANEL, activeforeground=Theme.TEXT_PRIMARY, font=("Consolas", 10), command=self._on_loop_toggle).pack(pady=4)
        
        # Controller
        ctrl_frame = tk.Frame(tab_settings, bg=Theme.PANEL, pady=8)
        ctrl_frame.pack(fill="x", padx=8, pady=4)
        tk.Label(ctrl_frame, text="◂ CONTROLLER ▸", bg=Theme.PANEL, fg=Theme.TEXT_DIM, font=("Consolas", 8)).pack()
        
        ctrl_toggle_row = tk.Frame(ctrl_frame, bg=Theme.PANEL)
        ctrl_toggle_row.pack(pady=4)
        self.ctrl_var = tk.BooleanVar(value=self.cfg["controller_enabled"])
        ctrl_status = "[READY]" if PYGAME_OK else "[pip install pygame]"
        ctrl_color = Theme.NOMINAL if PYGAME_OK else Theme.CRITICAL
        
        tk.Checkbutton(ctrl_toggle_row, text="Enable Controller", variable=self.ctrl_var, bg=Theme.PANEL, fg=Theme.TEXT_PRIMARY, selectcolor=Theme.DEEP, activebackground=Theme.PANEL, activeforeground=Theme.TEXT_PRIMARY, font=("Consolas", 10), state="normal" if PYGAME_OK else "disabled", command=self._on_controller_toggle).pack(side="left")
        tk.Label(ctrl_toggle_row, text=ctrl_status, bg=Theme.PANEL, fg=ctrl_color, font=("Consolas", 8)).pack(side="left", padx=8)
        
        ctrl_btn_row = tk.Frame(ctrl_frame, bg=Theme.PANEL)
        ctrl_btn_row.pack(pady=4)
        ctrl_btns = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "BACK", "START", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"]
        
        for label, cfg_key, color in [("START:", "controller_start", Theme.NOMINAL), ("STOP:", "controller_stop", Theme.CRITICAL), ("◀FAST:", "controller_faster", Theme.CAUTION), ("SLOW▶:", "controller_slower", Theme.CAUTION)]:
            fr = tk.Frame(ctrl_btn_row, bg=Theme.PANEL)
            fr.pack(side="left", padx=4)
            tk.Label(fr, text=label, bg=Theme.PANEL, fg=color, font=("Consolas", 8, "bold")).pack(side="left")
            var = tk.StringVar(value=self.cfg[cfg_key])
            cb = ttk.Combobox(fr, textvariable=var, values=ctrl_btns, width=8, state="readonly")
            cb.pack(side="left", padx=2)
            cb.bind("<<ComboboxSelected>>", lambda e, k=cfg_key, v=var: self._on_controller_btn_change(k, v.get()))
            setattr(self, f"{cfg_key}_var", var)
        
        # Save Button
        save_frame = tk.Frame(tab_settings, bg=Theme.SPACE)
        save_frame.pack(fill="x", padx=8, pady=12)
        tk.Button(save_frame, text="💾 SAVE SETTINGS", bg=Theme.NOMINAL, fg=Theme.SPACE, font=("Consolas", 11, "bold"), relief="flat", cursor="hand2", height=2, command=self._save_config).pack(fill="x", pady=2)
        tk.Button(save_frame, text="🔄 RESET TO DEFAULTS", bg=Theme.CAUTION, fg=Theme.SPACE, font=("Consolas", 10, "bold"), relief="flat", cursor="hand2", height=1, command=self._reset_defaults).pack(fill="x", pady=2)
    
    def _section(self, title, color):
        fr = tk.Frame(self.params_frame, bg=Theme.SPACE)
        fr.pack(fill="x", pady=(12, 4))
        tk.Frame(fr, bg=color, width=4, height=16).pack(side="left", padx=(0, 8))
        tk.Label(fr, text=title, bg=Theme.SPACE, fg=color, font=("Consolas", 9, "bold")).pack(side="left")
    
    def _slider(self, key, label, min_v, max_v, unit="ms"):
        def on_change(v, k=key):
            self.cfg[k] = v
            self._auto_save()
        
        s = TelemetrySlider(
            self.params_frame, label, min_v, max_v, self.cfg.get(key, min_v),
            unit=unit, on_change=on_change
        )
        s.pack(fill="x", pady=1)
        self.sliders[key] = s
    
    def _auto_save(self):
        # Debounced auto-save (waits 1 sec after last change)
        if hasattr(self, '_save_timer'):
            self.root.after_cancel(self._save_timer)
        self._save_timer = self.root.after(1000, self._save_config)
    
    def _log(self, msg, level="INFO"):
        if hasattr(self, 'log_panel'):
            self.log_panel.log(msg, level)
    
    def _set_phase(self, phase):
        self.root.after(0, lambda: [ind.set_active(k == phase) for k, ind in self.phases.items()])
    
    def _on_net_mode_change(self):
        mode_str = self.net_mode_var.get()
        self.cfg["network_mode"] = mode_str
        self.network.mode = NetworkMode.PYDIVERT if mode_str == "pydivert" else NetworkMode.FIREWALL
        self.status.set_network(self.network.mode.value, "ONLINE")
        self._log(f"Network mode: {self.network.mode.value}")
    
    def _on_keybind_change(self, key, value):
        self.cfg[key] = value
        self.launch_btn.configure(text=f"◆ LAUNCH [{self.cfg['key_start']}]")
        self.pause_btn.configure(text=f"❚❚ PAUSE [{self.cfg['key_pause']}]")
        self.abort_btn.configure(text=f"■ ABORT [{self.cfg['key_stop']}]")
        self._log(f"Keybind: {key} = {value}")
    
    def _on_loop_toggle(self):
        self.cfg["loop_enabled"] = self.loop_var.get()
        status = "ON" if self.cfg["loop_enabled"] else "OFF"
        self._log(f"Loop: {status}")
    
    def _on_ping_change(self, value):
        self.cfg["ping_offset"] = value
        self._log(f"Timing offset: {value}ms")
    
    def _adjust_timing(self, amount, reset=False):
        if reset:
            new_val = 0
        else:
            new_val = max(0, min(300, self.cfg["ping_offset"] + amount))
        self.cfg["ping_offset"] = new_val
        self.ping_slider.set(new_val)
        self._log(f"Timing offset: {new_val}ms")
    
    def _reset_defaults(self):
        defaults = {
            "charge_hold": 150,
            "cancel_hold": 50,
            "post_cancel_delay": 30,
            "dc_delay": 0,
            "dc_settle": 50,
            "inv_open": 400,
            "inv_settle": 150,
            "inv_grip": 100,
            "inv_drag": 600,
            "inv_drop": 100,
            "inv_close": 200,
            "throw_count": 2,
            "throw_hold": 49,
            "throw_delay": 49,
            "reconnect_on_throw": 1,
            "reconnect_delay": 25,
            "e_count": 10,
            "e_hold": 20,
            "e_delay": 20,
            "loop_delay": 800,
            "ping_offset": 0,
        }
        for key, val in defaults.items():
            self.cfg[key] = val
            if key in self.sliders:
                self.sliders[key].set(val)
        self.ping_slider.set(0)
        self._save_config()
        self._log("Reset to defaults!")
    
    def _on_controller_toggle(self):
        self.cfg["controller_enabled"] = self.ctrl_var.get()
        if self.cfg["controller_enabled"] and PYGAME_OK:
            self._start_controller_thread()
            self._log("Controller: ENABLED")
        else:
            self._log("Controller: DISABLED")
    
    def _on_controller_btn_change(self, key, value):
        self.cfg[key] = value
        self._log(f"Controller: {key} = {value}")
    
    def _start_controller_thread(self):
        if not PYGAME_OK:
            return
        threading.Thread(target=self._controller_poll, daemon=True).start()
    
    def _controller_poll(self):
        BTN_MAP = {"A": 0, "B": 1, "X": 2, "Y": 3, "LB": 4, "RB": 5, "BACK": 6, "START": 7, "LT": -1, "RT": -2,
                   "DPAD_UP": -10, "DPAD_DOWN": -11, "DPAD_LEFT": -12, "DPAD_RIGHT": -13}
        
        joystick = None
        if pygame.joystick.get_count() > 0:
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
            self._log(f"Controller: {joystick.get_name()}")
        
        prev = {}
        
        def get_btn(name):
            btn = BTN_MAP.get(name, -99)
            if btn == -99 or not joystick: return False
            if btn == -1: return joystick.get_axis(2) > 0.5 if joystick.get_numaxes() > 2 else False
            if btn == -2: return joystick.get_axis(5) > 0.5 if joystick.get_numaxes() > 5 else False
            if btn <= -10 and joystick.get_numhats() > 0:
                hat = joystick.get_hat(0)
                if btn == -10: return hat[1] == 1
                if btn == -11: return hat[1] == -1
                if btn == -12: return hat[0] == -1
                if btn == -13: return hat[0] == 1
            if btn >= 0: return joystick.get_button(btn) if btn < joystick.get_numbuttons() else False
            return False
        
        while self.cfg["controller_enabled"] and PYGAME_OK:
            try:
                pygame.event.pump()
                if not joystick and pygame.joystick.get_count() > 0:
                    joystick = pygame.joystick.Joystick(0)
                    joystick.init()
                
                if joystick:
                    for key, action in [
                        ("controller_start", self._launch),
                        ("controller_stop", self._abort),
                        ("controller_faster", lambda: self._adjust_timing(-5)),
                        ("controller_slower", lambda: self._adjust_timing(5)),
                    ]:
                        pressed = get_btn(self.cfg[key])
                        if pressed and not prev.get(key):
                            self.root.after(0, action)
                        prev[key] = pressed
                
                time.sleep(0.05)
            except:
                time.sleep(0.5)
    
    def _on_hotkey(self, key):
        start = self.KEY_MAP.get(self.cfg["key_start"].upper())
        pause = self.KEY_MAP.get(self.cfg["key_pause"].upper())
        stop = self.KEY_MAP.get(self.cfg["key_stop"].upper())
        
        if key == start:
            self.root.after(0, self._launch)
        elif key == pause:
            self.root.after(0, self._toggle_pause)
        elif key == stop:
            self.root.after(0, self._abort)
    
    def _is_running(self):
        with self._lock:
            return self.running
    
    def _is_paused(self):
        with self._lock:
            return self.paused
    
    def _toggle_pause(self):
        with self._lock:
            if not self.running:
                return
            self.paused = not self.paused
        
        if self.paused:
            self.status.set_status("PAUSED", Theme.CAUTION)
            self.pause_btn.configure(text=f"▶ RESUME [{self.cfg['key_pause']}]", bg=Theme.STANDBY)
            self._log("Paused")
        else:
            self.status.set_status("ACTIVE", Theme.NOMINAL)
            self.pause_btn.configure(text=f"❚❚ PAUSE [{self.cfg['key_pause']}]", bg=Theme.CAUTION)
            self._log("Resumed")
    
    def _launch(self):
        with self._lock:
            if self.running:
                return
            self.running = True
            self.paused = False
        
        self.loop_count = 0
        self.mapper.calibrate(self.root.winfo_id())
        
        self.status.set_status("ACTIVE", Theme.NOMINAL)
        self.status.set_network(self.network.mode.value, "ONLINE")
        self.launch_btn.configure(bg=Theme.OFFLINE, state="disabled")
        
        self._log("Mission launched")
        threading.Thread(target=self._mission_loop, daemon=True).start()
    
    def _abort(self):
        with self._lock:
            self.running = False
            self.paused = False
        
        self.network.reconnect()
        
        # Release any held buttons
        try:
            user32.mouse_event(0x0004, 0, 0, 0, 0)  # Left up
            user32.mouse_event(0x0010, 0, 0, 0, 0)  # Right up
        except:
            pass
        
        self.status.set_status("ABORTED", Theme.CRITICAL)
        self.status.set_network(self.network.mode.value, "ONLINE")
        self.launch_btn.configure(bg=Theme.NOMINAL, state="normal")
        self.pause_btn.configure(text=f"❚❚ PAUSE [{self.cfg['key_pause']}]", bg=Theme.CAUTION)
        self._set_phase("")
        self._log("Aborted")
    
    def _sleep(self, ms: int) -> bool:
        if ms <= 0:
            return self._is_running()
        end = time.perf_counter() + ms / 1000.0
        while time.perf_counter() < end:
            if not self._is_running():
                return False
            while self._is_paused():
                if not self._is_running():
                    return False
                time.sleep(0.05)
            time.sleep(0.001)
        return True
    
    def _mission_loop(self):
        cfg = self.cfg
        
        while self._is_running():
            self.loop_count += 1
            self.root.after(0, lambda c=self.loop_count: self.status.set_loop(c))
            self._log(f"--- Cycle {self.loop_count} | Offset: {cfg.get('ping_offset', 0)}ms ---")
            
            try:
                # ══════════════════════════════════════════════════════════════════
                # PHASE 1: CHARGE - Hold left click
                # ══════════════════════════════════════════════════════════════════
                self._set_phase("charge")
                self._log("Charging (holding left)...")
                
                user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFT DOWN - HOLD IT!
                if not self._sleep(cfg["charge_hold"]):
                    user32.mouse_event(0x0004, 0, 0, 0, 0)
                    break
                
                # ══════════════════════════════════════════════════════════════════
                # PHASE 2: CANCEL - Right click WHILE holding left, then release
                # ══════════════════════════════════════════════════════════════════
                self._set_phase("cancel")
                self._log("Cancel (right click while holding left)")
                
                # Right click to cancel trajectory (LEFT IS STILL HELD!)
                user32.mouse_event(0x0008, 0, 0, 0, 0)  # RIGHT DOWN
                if not self._sleep(cfg["cancel_hold"]):
                    user32.mouse_event(0x0010, 0, 0, 0, 0)
                    user32.mouse_event(0x0004, 0, 0, 0, 0)
                    break
                user32.mouse_event(0x0010, 0, 0, 0, 0)  # RIGHT UP - cancel complete
                
                # Small delay THEN release left (after cancel registered)
                if not self._sleep(cfg["post_cancel_delay"]):
                    user32.mouse_event(0x0004, 0, 0, 0, 0)
                    break
                user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFT UP - now safe to release
                
                # ══════════════════════════════════════════════════════════════════
                # PHASE 3: DISCONNECT - Immediately after cancel
                # ══════════════════════════════════════════════════════════════════
                self._set_phase("network")
                
                if not self._sleep(cfg["dc_delay"]):
                    break
                
                self._log(">>> NETWORK DISCONNECT <<<")
                self.network.disconnect()
                self.root.after(0, lambda: self.status.set_network(self.network.mode.value, "BLOCKED"))
                
                # Apply ping offset to settle time
                offset = cfg.get("ping_offset", 0)
                settle_wait = cfg["dc_settle"] + offset
                self._log(f"Settle: {cfg['dc_settle']}+{offset}={settle_wait}ms")
                if not self._sleep(settle_wait):
                    break
                
                # ══════════════════════════════════════════════════════════════════
                # PHASE 4: INVENTORY - Open, drag, close
                # ══════════════════════════════════════════════════════════════════
                self._set_phase("inventory")
                self._log("Inventory drop")
                
                # Open inventory
                self.kb.press(Key.tab)
                time.sleep(0.05)
                self.kb.release(Key.tab)
                
                if not self._sleep(cfg["inv_open"]):
                    break
                
                # Get positions
                from_pos = self.mapper.translate(1502, 360)
                to_pos = self.mapper.translate(401, 506)
                
                # Move to item
                self.ms.position = from_pos
                if not self._sleep(cfg["inv_settle"]):
                    break
                
                # Grab item
                self.ms.press(Button.left)
                if not self._sleep(cfg["inv_grip"]):
                    self.ms.release(Button.left)
                    break
                
                # Smooth drag
                drag_ms = cfg["inv_drag"]
                steps = max(20, drag_ms // 15)
                fx, fy = from_pos
                tx, ty = to_pos
                
                for i in range(steps + 1):
                    if not self._is_running():
                        break
                    progress = i / steps
                    ease = 1 - pow(1 - progress, 3)
                    self.ms.position = (int(fx + (tx - fx) * ease), int(fy + (ty - fy) * ease))
                    time.sleep(drag_ms / 1000 / steps)
                
                # Drop item
                if not self._sleep(cfg["inv_drop"]):
                    self.ms.release(Button.left)
                    break
                self.ms.release(Button.left)
                
                # Close inventory
                if not self._sleep(cfg["inv_close"]):
                    break
                self.kb.press(Key.tab)
                time.sleep(0.05)
                self.kb.release(Key.tab)
                
                time.sleep(0.1)
                
                # ══════════════════════════════════════════════════════════════════
                # PHASE 5: THROW (multiple) + RECONNECT mid-throw
                # ══════════════════════════════════════════════════════════════════
                self._set_phase("combat")
                self._log(f"Throwing - reconnect mid-throw #{cfg['reconnect_on_throw']}")
                
                for i in range(cfg["throw_count"]):
                    if not self._is_running():
                        break
                    
                    # Start throw
                    user32.mouse_event(0x0002, 0, 0, 0, 0)  # Left DOWN
                    
                    # If this is the throw to reconnect on, reconnect MID-CLICK
                    if i + 1 == cfg["reconnect_on_throw"]:
                        # Apply ping offset to reconnect timing
                        offset = cfg.get("ping_offset", 0)
                        reconnect_wait = cfg["reconnect_delay"] + offset
                        self._log(f"Reconnect: {cfg['reconnect_delay']}+{offset}={reconnect_wait}ms")
                        if not self._sleep(reconnect_wait):
                            user32.mouse_event(0x0004, 0, 0, 0, 0)
                            break
                        self._log(">>> RECONNECT <<<")
                        self.network.reconnect()
                        self.root.after(0, lambda: self.status.set_network(self.network.mode.value, "ONLINE"))
                    
                    # Finish this throw
                    if not self._sleep(cfg["throw_hold"]):
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                        break
                    user32.mouse_event(0x0004, 0, 0, 0, 0)  # Left UP
                    
                    if not self._sleep(cfg["throw_delay"]):
                        break
                
                # ══════════════════════════════════════════════════════════════════
                # PHASE 6: PICKUP - E-spam
                # ══════════════════════════════════════════════════════════════════
                self._set_phase("pickup")
                self._log("E-spam pickup")
                
                for _ in range(cfg["e_count"]):
                    if not self._is_running():
                        break
                    self.kb.press('e')
                    if not self._sleep(cfg["e_hold"]):
                        self.kb.release('e')
                        break
                    self.kb.release('e')
                    if not self._sleep(cfg["e_delay"]):
                        break
                
                # ══════════════════════════════════════════════════════════════════
                # CYCLE COMPLETE
                # ══════════════════════════════════════════════════════════════════
                self._set_phase("")
                
                # Check if loop is disabled - run once and stop
                if not self.cfg["loop_enabled"]:
                    self._log("Single cycle complete")
                    break
                
                if not self._sleep(cfg["loop_delay"]):
                    break
                
            except Exception as e:
                self._log(f"Error: {e}")
                time.sleep(0.5)
        
        # Cleanup
        with self._lock:
            self.running = False
        self.network.reconnect()
        self._set_phase("")
        self.root.after(0, lambda: self.status.set_network(self.network.mode.value, "ONLINE"))
        self.root.after(0, lambda: self.pause_btn.configure(text=f"❚❚ PAUSE [{self.cfg['key_pause']}]", bg=Theme.CAUTION))
        self.root.after(0, lambda: self.launch_btn.configure(bg=Theme.NOMINAL, state="normal"))
        self.root.after(0, lambda: self.status.set_status("READY", Theme.STANDBY))
        self._log("Mission complete")
    
    def _shutdown(self):
        self._abort()
        self._save_config()
        self.network.cleanup()
        self.root.destroy()
        sys.exit(0)
    
    def run(self):
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    WolfpackApp().run()
