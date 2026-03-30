#!/usr/bin/env python3
"""
VidCal — Video Calibration Tool
EBU/SMPTE Chart Analysis · LUT Generation · AviSynth+ Integration
Unterstützt: Blackmagic, I/O Data GV-USB2, Cam Link 4K, generic VfW
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
import os, sys, subprocess, threading, json
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Referenzwerte EBU/SMPTE Colour Bars (8-bit, BT.601)
# ─────────────────────────────────────────────────────────────────────────────

EBU_BARS_75 = [
    ("White 75%",   (180, 180, 180)),
    ("Yellow 75%",  (180, 180,  16)),
    ("Cyan 75%",    ( 16, 180, 180)),
    ("Green 75%",   ( 16, 180,  16)),
    ("Magenta 75%", (180,  16, 180)),
    ("Red 75%",     (180,  16,  16)),
    ("Blue 75%",    ( 16,  16, 180)),
    ("Black",       ( 16,  16,  16)),
]

EBU_BARS_100 = [
    ("White 100%",  (235, 235, 235)),
    ("Yellow 100%", (235, 235,  16)),
    ("Cyan 100%",   ( 16, 235, 235)),
    ("Green 100%",  ( 16, 235,  16)),
    ("Magenta 100%",(235,  16, 235)),
    ("Red 100%",    (235,  16,  16)),
    ("Blue 100%",   ( 16,  16, 235)),
    ("Black",       ( 16,  16,  16)),
]

SMPTE_BARS = [
    ("White",    (235, 235, 235)),
    ("Yellow",   (235, 235,  16)),
    ("Cyan",     ( 16, 235, 235)),
    ("Green",    ( 16, 235,  16)),
    ("Magenta",  (235,  16, 235)),
    ("Red",      (235,  16,  16)),
    ("Blue",     ( 16,  16, 235)),
    ("-I",       ( 16,  59, 133)),
    ("White sub",(235, 235, 235)),
    ("+Q",       ( 61,  16, 106)),
    ("Black",    ( 16,  16,  16)),
]

# ─────────────────────────────────────────────────────────────────────────────
# Capture-Gerät-Profile
# ─────────────────────────────────────────────────────────────────────────────

CAPTURE_DEVICES = {
    "Blackmagic UltraStudio Mini Recorder": {
        "avisynth": 'DirectShowSource("blackmagic://0", fps=25, audio=false)',
        "ffmpeg":   "-f dshow -i video=\"Blackmagic WDM Capture\"",
    },
    "Blackmagic Intensity 4K": {
        "avisynth": 'DirectShowSource("blackmagic://1", fps=25, audio=false)',
        "ffmpeg":   "-f dshow -i video=\"Blackmagic WDM Capture\"",
    },
    "I/O Data GV-USB2": {
        "avisynth": 'AviSource("gvusb2://0")',
        "ffmpeg":   "-f dshow -i video=\"GV-USB2\"",
    },
    "Elgato Cam Link 4K": {
        "avisynth": 'DirectShowSource("camlink://0", fps=25, audio=false)',
        "ffmpeg":   "-f dshow -i video=\"Cam Link 4K\"",
    },
    "Generic VfW / DirectShow": {
        "avisynth": 'DirectShowSource("vfw://0", fps=25, audio=false)',
        "ffmpeg":   "-f dshow -i video=\"0\"",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Testbild-Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_ebu_bars(width=1920, height=1080, mode="75%"):
    """Generiert EBU Colour Bars als numpy-Array (BGR)."""
    bars = EBU_BARS_75 if mode == "75%" else EBU_BARS_100
    img = np.zeros((height, width, 3), dtype=np.uint8)
    bar_w = width // len(bars)
    for i, (name, (r, g, b)) in enumerate(bars):
        x0 = i * bar_w
        x1 = x0 + bar_w if i < len(bars) - 1 else width
        img[:, x0:x1] = (b, g, r)  # OpenCV = BGR
    return img

def generate_smpte_bars(width=1920, height=1080):
    """Generiert SMPTE RP 219 Colour Bars (vereinfacht)."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    bars_top = SMPTE_BARS[:7]
    bar_w = width // len(bars_top)
    h_top = int(height * 0.67)
    for i, (name, (r, g, b)) in enumerate(bars_top):
        x0 = i * bar_w
        x1 = x0 + bar_w if i < len(bars_top) - 1 else width
        img[:h_top, x0:x1] = (b, g, r)
    # Untere Streifen
    img[h_top:, :] = (16, 16, 16)
    return img

def generate_grey_ramp(width=1920, height=1080, steps=16):
    """Graukeil mit N Stufen."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    step_w = width // steps
    for i in range(steps):
        val = int(i * 255 / (steps - 1))
        x0 = i * step_w
        x1 = x0 + step_w if i < steps - 1 else width
        img[:, x0:x1] = (val, val, val)
    return img

# Macbeth ColorChecker — 24 Patches, D50-Referenzwerte (sRGB 8-bit)
MACBETH_PATCHES = [
    # Reihe 1
    ("Dark Skin",        ( 115,  82,  68)),
    ("Light Skin",       (194, 150, 130)),
    ("Blue Sky",         ( 98, 122, 157)),
    ("Foliage",          ( 87, 108,  67)),
    ("Blue Flower",      (133, 128, 177)),
    ("Bluish Green",     (103, 189, 170)),
    # Reihe 2
    ("Orange",           (214, 126,  44)),
    ("Purplish Blue",    ( 80,  91, 166)),
    ("Moderate Red",     (193,  90,  99)),
    ("Purple",           ( 94,  60, 108)),
    ("Yellow Green",     (157, 188,  64)),
    ("Orange Yellow",    (224, 163,  46)),
    # Reihe 3
    ("Blue",             ( 56,  61, 150)),
    ("Green",            ( 70, 148,  73)),
    ("Red",              (175,  54,  60)),
    ("Yellow",           (231, 199,  31)),
    ("Magenta",          (187,  86, 149)),
    ("Cyan",             (  8, 133, 161)),
    # Reihe 4 — Graustufen
    ("White",            (243, 243, 242)),
    ("Neutral 8",        (200, 200, 200)),
    ("Neutral 6.5",      (160, 160, 160)),
    ("Neutral 5",        (122, 122, 121)),
    ("Neutral 3.5",      ( 85,  85,  85)),
    ("Black",            ( 52,  52,  52)),
]

def generate_macbeth_chart(width=1920, height=1080):
    """
    Generiert einen Macbeth ColorChecker (4×6 Patches) als numpy-Array (BGR).
    Mit Patch-Beschriftung und weißem Rand.
    """
    img = np.full((height, width, 3), 30, dtype=np.uint8)  # dunkelgrauer Hintergrund

    cols, rows = 6, 4
    margin_x = int(width  * 0.04)
    margin_y = int(height * 0.06)
    gap      = int(width  * 0.012)

    patch_w = (width  - 2 * margin_x - (cols - 1) * gap) // cols
    patch_h = (height - 2 * margin_y - (rows - 1) * gap) // rows

    for idx, (name, (r, g, b)) in enumerate(MACBETH_PATCHES):
        row = idx // cols
        col = idx  % cols
        x0  = margin_x + col * (patch_w + gap)
        y0  = margin_y + row * (patch_h + gap)
        x1, y1 = x0 + patch_w, y0 + patch_h

        # Patch füllen
        img[y0:y1, x0:x1] = (b, g, r)

        # Rahmen
        cv2.rectangle(img, (x0, y0), (x1, y1), (200, 200, 200), 1)

        # Patch-Name (klein, unten im Patch)
        font_scale = max(0.28, patch_w / 480)
        text_y = y1 - 6
        cv2.putText(img, name, (x0 + 4, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 2)
        cv2.putText(img, name, (x0 + 4, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (240, 240, 240), 1)

    # Titel
    cv2.putText(img, "Macbeth ColorChecker — D50 Reference (sRGB)",
                (margin_x, margin_y - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1)
    return img

def analyze_macbeth_from_frame(frame_bgr, cols=6, rows=4):
    """
    Misst die 24 Macbeth-Patches aus einem Frame.
    Erwartet, dass der Chart das gesamte Bild ausfüllt (wie von generate_macbeth_chart).
    Gibt Liste von (name, ref_rgb, measured_rgb, delta_rgb) zurück.
    """
    h, w = frame_bgr.shape[:2]
    margin_x = int(w  * 0.04)
    margin_y = int(h  * 0.06)
    gap      = int(w  * 0.012)
    patch_w  = (w - 2 * margin_x - (cols - 1) * gap) // cols
    patch_h  = (h - 2 * margin_y - (rows - 1) * gap) // rows

    results = []
    for idx, (name, ref_rgb) in enumerate(MACBETH_PATCHES):
        row = idx // cols
        col = idx  % cols
        x0  = margin_x + col * (patch_w + gap) + patch_w // 5
        y0  = margin_y + row * (patch_h + gap) + patch_h // 5
        x1  = x0 + patch_w * 3 // 5
        y1  = y0 + patch_h * 3 // 5
        roi = frame_bgr[y0:y1, x0:x1]
        mean_bgr = cv2.mean(roi)[:3]
        measured_rgb = (int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0]))
        delta = tuple(measured_rgb[i] - ref_rgb[i] for i in range(3))
        results.append((name, ref_rgb, measured_rgb, delta))
    return results

# ─────────────────────────────────────────────────────────────────────────────
# Chart-Analyse
# ─────────────────────────────────────────────────────────────────────────────

def analyze_bars_from_frame(frame_bgr, mode="EBU 75%"):
    """
    Misst Farbwerte aus den Balken-Bereichen und vergleicht mit Referenz.
    Gibt Liste von (name, ref_rgb, measured_rgb, delta_rgb) zurück.
    """
    if mode == "EBU 75%":
        bars = EBU_BARS_75
    elif mode == "EBU 100%":
        bars = EBU_BARS_100
    else:
        bars = SMPTE_BARS[:7]

    h, w = frame_bgr.shape[:2]
    results = []
    bar_w = w // len(bars)

    for i, (name, ref_rgb) in enumerate(bars):
        x0 = i * bar_w + bar_w // 4
        x1 = x0 + bar_w // 2
        y0 = h // 4
        y1 = 3 * h // 4
        roi = frame_bgr[y0:y1, x0:x1]
        mean_bgr = cv2.mean(roi)[:3]
        measured_rgb = (int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0]))
        delta = (
            measured_rgb[0] - ref_rgb[0],
            measured_rgb[1] - ref_rgb[1],
            measured_rgb[2] - ref_rgb[2],
        )
        results.append((name, ref_rgb, measured_rgb, delta))
    return results

def calc_gamma_from_grey_ramp(frame_bgr, steps=16):
    """Schätzt Gamma aus Graukeil-Analyse."""
    h, w = frame_bgr.shape[:2]
    step_w = w // steps
    measured = []
    for i in range(steps):
        x0 = i * step_w + step_w // 4
        x1 = x0 + step_w // 2
        roi = frame_bgr[h//4:3*h//4, x0:x1]
        val = float(cv2.mean(roi)[0]) / 255.0
        measured.append(val)

    # Einfache Gamma-Schätzung via Least Squares
    expected = [i / (steps - 1) for i in range(steps)]
    gammas = []
    for e, m in zip(expected[1:-1], measured[1:-1]):
        if e > 0 and m > 0:
            try:
                g = np.log(m) / np.log(e)
                gammas.append(g)
            except:
                pass
    return float(np.median(gammas)) if gammas else 1.0

# ─────────────────────────────────────────────────────────────────────────────
# LUT-Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_3dlut(analysis_results, gamma_correction=1.0, lut_size=33, output_path="correction.cube"):
    """
    Generiert eine 3D-LUT (.cube) aus den Analyse-Ergebnissen.
    """
    # Durchschnittliche RGB-Abweichungen aus allen Patches
    deltas = [d for (_, _, _, d) in analysis_results]
    avg_delta = (
        np.mean([d[0] for d in deltas]),
        np.mean([d[1] for d in deltas]),
        np.mean([d[2] for d in deltas]),
    )

    with open(output_path, "w") as f:
        f.write(f"# VidCal — Auto-generierte Korrektur-LUT\n")
        f.write(f"# Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Gamma-Korrektur: {gamma_correction:.4f}\n")
        f.write(f"# Durchschn. Delta RGB: {avg_delta[0]:.1f} / {avg_delta[1]:.1f} / {avg_delta[2]:.1f}\n\n")
        f.write(f"LUT_3D_SIZE {lut_size}\n\n")

        for b in range(lut_size):
            for g in range(lut_size):
                for r in range(lut_size):
                    # Eingangswert
                    ri = r / (lut_size - 1)
                    gi = g / (lut_size - 1)
                    bi = b / (lut_size - 1)
                    # Gamma-Korrektur
                    if gamma_correction != 1.0:
                        ri = ri ** (1.0 / gamma_correction)
                        gi = gi ** (1.0 / gamma_correction)
                        bi = bi ** (1.0 / gamma_correction)
                    # Farbkorrektur (normalisierte Abweichung)
                    ro = np.clip(ri - avg_delta[0] / 255.0, 0, 1)
                    go = np.clip(gi - avg_delta[1] / 255.0, 0, 1)
                    bo = np.clip(bi - avg_delta[2] / 255.0, 0, 1)
                    f.write(f"{ro:.6f} {go:.6f} {bo:.6f}\n")

    return output_path

# ─────────────────────────────────────────────────────────────────────────────
# AviSynth-Script-Generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_avisynth_script(device_name, lut_path, output_avi, gamma,
                              interlaced=True, deinterlace_qtgmc=False,
                              width=1920, height=1080, fps=25):
    device = CAPTURE_DEVICES.get(device_name, CAPTURE_DEVICES["Generic VfW / DirectShow"])
    lut_abs = str(Path(lut_path).resolve()).replace("\\", "\\\\")
    out_abs  = str(Path(output_avi).resolve()).replace("\\", "\\\\")

    lines = [
        "# VidCal — Auto-generiertes Korrektur-Script",
        f"# Gerät: {device_name}",
        f"# Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "# === Quelle ===",
        device["avisynth"],
        "",
        "# === Farbraum ===",
        "ConvertToRGB32()",
        "",
    ]

    if gamma != 1.0:
        g = round(gamma, 4)
        lines += [
            f"# === Gamma-Korrektur (gemessen: {g}) ===",
            f'Levels(0, {g}, 255, 0, 255)',
            "",
        ]

    lines += [
        f'# === 3D-LUT Farbkorrektur ===',
        f'# Hinweis: "Hable_3DLUT" benötigt das AviSynth+ Plugin "AvsLUT" oder äquivalent',
        f'# LUT-Datei: {lut_abs}',
        f'# Alternativ mit FFmpeg: ffmpeg -i input.avi -vf "lut3d={lut_abs}" ...',
        "",
    ]

    if interlaced:
        if deinterlace_qtgmc:
            lines += [
                "# === QTGMC Deinterlace (vor Encode) ===",
                'Import("QTGMC.avs")',
                "QTGMC(Preset=\"Slow\", TFF=true)",
                "",
            ]
        else:
            lines += [
                "# === Interlaced-Ausgabe (kein Deinterlace) ===",
                "AssumeTFF()",
                "",
            ]

    lines += [
        "# === Ausgabe ===",
        f'# Speichern mit: mencoder / ffmpeg (siehe unten)',
        "",
        "# Beispiel FFmpeg-Befehl für H.264:",
    ]

    if interlaced and not deinterlace_qtgmc:
        lines.append(f'# ffmpeg -i script.avs -c:v libx264 -flags +ildct+ilme -top 1 -crf 18 "{out_abs}"')
    else:
        lines.append(f'# ffmpeg -i script.avs -c:v libx264 -crf 18 "{out_abs}"')

    script = "\n".join(lines)

    avs_path = output_avi.replace(".avi", ".avs").replace(".mkv", ".avs")
    with open(avs_path, "w", encoding="utf-8") as f:
        f.write(script)
    return avs_path, script

# ─────────────────────────────────────────────────────────────────────────────
# Testbild-Vorschau & Analyse
# ─────────────────────────────────────────────────────────────────────────────

def find_ffmpeg():
    """Findet FFmpeg — zuerst gebündelt neben der EXE, dann im System-PATH."""
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    bundled = base / "ffmpeg" / "ffmpeg.exe"
    if bundled.exists():
        return str(bundled)
    return "ffmpeg"  # Fallback: System-PATH

def enumerate_video_devices():
    """
    Listet alle DirectShow Video-Geräte via FFmpeg auf.
    Gibt (devices_list, raw_output) zurück.
    """
    import re

    # Auf Windows: kein Console-Fenster öffnen (wichtig bei --windowed PyInstaller)
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    devices = []
    raw = ""
    ffmpeg = find_ffmpeg()

    try:
        result = subprocess.run(
            [ffmpeg, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            **kwargs
        )
        # FFmpeg schreibt Geräteliste nach stderr
        raw = result.stderr.decode("utf-8", errors="replace")

        in_video = False
        for line in raw.splitlines():
            if "DirectShow video devices" in line:
                in_video = True
                continue
            if "DirectShow audio devices" in line or "DirectShow video+audio devices" in line:
                # video+audio Geräte auch erfassen
                if "video+audio" in line:
                    in_video = True
                else:
                    in_video = False
                continue
            if in_video:
                m = re.search(r'"([^"]+)"', line)
                if m and "Alternative name" not in line and "@device" not in line:
                    name = m.group(1)
                    lower = name.lower()
                    if any(k in lower for k in ["1394", "firewire", "dv", "ohci", "msdv"]):
                        label = f"[IEEE 1394]  {name}"
                    elif any(k in lower for k in ["blackmagic", "intensity", "ultrastudio", "decklink"]):
                        label = f"[Blackmagic]  {name}"
                    elif any(k in lower for k in ["gv-usb", "gvusb"]):
                        label = f"[I/O Data]  {name}"
                    elif any(k in lower for k in ["cam link", "camlink", "elgato"]):
                        label = f"[Elgato]  {name}"
                    elif any(k in lower for k in ["virtual", "obs", "vcam", "loopback"]):
                        label = f"[VirtualCam]  {name}"
                    elif any(k in lower for k in ["magewell", "aja", "matrox"]):
                        label = f"[Pro Capture]  {name}"
                    else:
                        label = f"[DirectShow]  {name}"
                    if label not in devices:
                        devices.append(label)

    except FileNotFoundError:
        raw = f"FEHLER: FFmpeg nicht gefunden unter: {ffmpeg}"
    except Exception as e:
        raw = f"FEHLER: {e}"

    return devices, raw

def frame_to_photoimage(frame_bgr, max_w=900):
    from PIL import Image, ImageTk
    h, w = frame_bgr.shape[:2]
    scale = min(1.0, max_w / w)
    nw, nh = int(w * scale), int(h * scale)
    frame_rgb = cv2.cvtColor(cv2.resize(frame_bgr, (nw, nh)), cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)
    return ImageTk.PhotoImage(img)

# ─────────────────────────────────────────────────────────────────────────────
# Hauptfenster
# ─────────────────────────────────────────────────────────────────────────────

class VidCal(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🎨 VidCal — Video Calibration Tool")
        self.minsize(1000, 700)
        self.configure(bg="#1e1e1e")

        self._analysis_results = []
        self._gamma = 1.0
        self._lut_path = None
        self._current_frame = None

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background="#1e1e1e")
        style.configure("TNotebook.Tab", background="#2d2d2d", foreground="white", padding=[10, 4])
        style.map("TNotebook.Tab", background=[("selected", "#3c3c3c")])
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#d4d4d4")
        style.configure("TButton", background="#3c3c3c", foreground="white")
        style.configure("TCombobox", fieldbackground="#2d2d2d", foreground="white")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._tab_testbild  = ttk.Frame(nb)
        self._tab_analyse   = ttk.Frame(nb)
        self._tab_lut       = ttk.Frame(nb)
        self._tab_avisynth  = ttk.Frame(nb)

        nb.add(self._tab_testbild,  text="🖼  Testbilder")
        nb.add(self._tab_analyse,   text="🔍  Analyse")
        nb.add(self._tab_lut,       text="🎛  LUT-Generierung")
        nb.add(self._tab_avisynth,  text="📄  AviSynth-Script")

        self._build_tab_testbild()
        self._build_tab_analyse()
        self._build_tab_lut()
        self._build_tab_avisynth()

    # ── Tab 1: Testbilder ────────────────────────────────────────────────────

    def _build_tab_testbild(self):
        f = self._tab_testbild
        row = 0

        tk.Label(f, text="Testbild-Generator", bg="#1e1e1e", fg="white",
                 font=("Segoe UI", 13, "bold")).grid(row=row, column=0, columnspan=3,
                 sticky="w", padx=12, pady=(12,4))
        row += 1

        tk.Label(f, text="Typ:", bg="#1e1e1e", fg="#d4d4d4").grid(row=row, column=0, padx=12, pady=4, sticky="w")
        self._tb_mode = ttk.Combobox(f, values=[
            "EBU Bars 75%", "EBU Bars 100%", "SMPTE RP219 Bars",
            "Graukeil 16 Stufen", "Graukeil 32 Stufen",
            "Macbeth ColorChecker",
        ], state="readonly", width=28)
        self._tb_mode.current(0)
        self._tb_mode.grid(row=row, column=1, padx=4, pady=4, sticky="w")
        row += 1

        tk.Label(f, text="Auflösung:", bg="#1e1e1e", fg="#d4d4d4").grid(row=row, column=0, padx=12, pady=4, sticky="w")
        self._tb_res = ttk.Combobox(f, values=["1920×1080", "1280×720", "720×576 (PAL)", "720×480 (NTSC)"],
                                     state="readonly", width=28)
        self._tb_res.current(0)
        self._tb_res.grid(row=row, column=1, padx=4, pady=4, sticky="w")
        row += 1

        # Ausgabe-Gerät
        tk.Label(f, text="Ausgabe-Gerät:", bg="#1e1e1e", fg="#d4d4d4").grid(
            row=row, column=0, padx=12, pady=4, sticky="w")
        self._tb_device_var = tk.StringVar(value="— Geräte werden geladen… —")
        self._tb_device_cb = ttk.Combobox(f, textvariable=self._tb_device_var,
                                           state="readonly", width=46)
        self._tb_device_cb.grid(row=row, column=1, padx=4, pady=4, sticky="w")
        btn_dev_frame = tk.Frame(f, bg="#1e1e1e")
        btn_dev_frame.grid(row=row, column=2, padx=4, sticky="w")
        tk.Button(btn_dev_frame, text="🔄", command=self._refresh_devices,
                  bg="#3c3c3c", fg="white", relief="flat", width=3).pack(side="left", padx=2)
        tk.Button(btn_dev_frame, text="🔍 Diagnose", command=self._show_device_diagnostics,
                  bg="#3c3c3c", fg="white", relief="flat", padx=6).pack(side="left", padx=2)
        row += 1

        btn_frame = tk.Frame(f, bg="#1e1e1e")
        btn_frame.grid(row=row, column=0, columnspan=3, padx=10, pady=8, sticky="w")
        tk.Button(btn_frame, text="▶ Vorschau", command=self._preview_testbild,
                  bg="#007acc", fg="white", relief="flat", padx=12, pady=4).pack(side="left", padx=4)
        tk.Button(btn_frame, text="💾 Als PNG speichern", command=self._save_testbild,
                  bg="#3c3c3c", fg="white", relief="flat", padx=12, pady=4).pack(side="left", padx=4)
        tk.Button(btn_frame, text="📤 An Capture-Board ausgeben", command=self._output_testbild,
                  bg="#3c3c3c", fg="white", relief="flat", padx=12, pady=4).pack(side="left", padx=4)
        row += 1

        self._tb_output_status = tk.Label(f, text="", bg="#1e1e1e", fg="#4ec9b0",
                                           font=("Segoe UI", 10))
        self._tb_output_status.grid(row=row, column=0, columnspan=3, padx=12, sticky="w")
        row += 1

        self._tb_canvas = tk.Label(f, bg="#111", relief="flat")
        self._tb_canvas.grid(row=row, column=0, columnspan=3, padx=10, pady=8, sticky="nsew")
        f.rowconfigure(row, weight=1)
        f.columnconfigure(2, weight=1)

        # Geräte beim Start laden
        self.after(300, self._refresh_devices)

    def _get_testbild_frame(self):
        mode = self._tb_mode.get()
        res_str = self._tb_res.get()
        res_map = {
            "1920×1080": (1920, 1080),
            "1280×720":  (1280, 720),
            "720×576 (PAL)": (720, 576),
            "720×480 (NTSC)": (720, 480),
        }
        w, h = res_map.get(res_str, (1920, 1080))
        if "75%" in mode:      return generate_ebu_bars(w, h, "75%")
        if "100%" in mode:     return generate_ebu_bars(w, h, "100%")
        if "SMPTE" in mode:    return generate_smpte_bars(w, h)
        if "16" in mode:       return generate_grey_ramp(w, h, 16)
        if "32" in mode:       return generate_grey_ramp(w, h, 32)
        if "Macbeth" in mode:  return generate_macbeth_chart(w, h)
        return generate_ebu_bars(w, h)

    def _preview_testbild(self):
        frame = self._get_testbild_frame()
        self._tb_photo = frame_to_photoimage(frame)
        self._tb_canvas.configure(image=self._tb_photo)

    def _save_testbild(self):
        frame = self._get_testbild_frame()
        path = filedialog.asksaveasfilename(defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("BMP", "*.bmp")],
            title="Testbild speichern")
        if path:
            cv2.imwrite(path, frame)
            messagebox.showinfo("Gespeichert", f"Testbild gespeichert:\n{path}")

    def _refresh_devices(self):
        """Erkennt alle DirectShow Video-Geräte (inkl. IEEE 1394 / FireWire) via FFmpeg."""
        self._tb_output_status.config(text="⏳ Suche Capture-Geräte…")
        self.update_idletasks()

        def worker():
            devices, raw = enumerate_video_devices()
            self._last_ffmpeg_raw = raw  # für Diagnose
            def update():
                if devices:
                    self._tb_device_cb["values"] = devices
                    self._tb_device_cb.current(0)
                    self._tb_output_status.config(
                        text=f"✅ {len(devices)} Gerät(e) gefunden")
                else:
                    self._tb_device_cb["values"] = ["(kein Gerät gefunden)"]
                    self._tb_device_cb.current(0)
                    self._tb_output_status.config(
                        text="⚠️  Keine Geräte — 'Diagnose' für Details")
            self.after(0, update)

        threading.Thread(target=worker, daemon=True).start()

    def _show_device_diagnostics(self):
        """Zeigt den rohen FFmpeg-Output zur Diagnose."""
        raw = getattr(self, '_last_ffmpeg_raw', '(noch keine Suche durchgeführt)')
        ffmpeg = find_ffmpeg()
        win = tk.Toplevel(self)
        win.title("FFmpeg Diagnose — DirectShow Geräte")
        win.configure(bg="#1e1e1e")
        win.geometry("800x500")
        tk.Label(win, text=f"FFmpeg Pfad: {ffmpeg}",
                 bg="#1e1e1e", fg="#4ec9b0", font=("Consolas", 9)).pack(anchor="w", padx=10, pady=(8,2))
        tk.Label(win, text="Roher FFmpeg-Output (stderr):",
                 bg="#1e1e1e", fg="#d4d4d4", font=("Segoe UI", 9)).pack(anchor="w", padx=10)
        txt = tk.Text(win, bg="#111", fg="#d4d4d4", font=("Consolas", 8), wrap="none")
        txt.pack(fill="both", expand=True, padx=10, pady=8)
        txt.insert("end", raw if raw else "(kein Output — FFmpeg gefunden?)")
        txt.config(state="disabled")
        sb = ttk.Scrollbar(win, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)

    def _output_testbild(self):
        """Gibt das aktuelle Testbild als Vollbild-Loop an das gewählte Capture-Gerät aus."""
        frame = self._get_testbild_frame()
        device = self._tb_device_var.get()
        if not device or "kein Gerät" in device or "geladen" in device:
            messagebox.showwarning("Kein Gerät", "Bitte zuerst ein Ausgabe-Gerät wählen.\n"
                "Klicke 🔄 um Geräte neu zu suchen.")
            return

        # Testbild als temporäre PNG speichern
        tmp_png = os.path.join(os.path.dirname(sys.executable)
                               if getattr(sys, 'frozen', False) else os.getcwd(),
                               "vidcal_testbild_tmp.png")
        cv2.imwrite(tmp_png, frame)

        # FFmpeg-Befehl: Bild als Endlosschleife an DirectShow-Gerät
        ffmpeg = find_ffmpeg()
        cmd = (
            f'"{ffmpeg}" -loop 1 -re -i "{tmp_png}" '
            f'-f dshow -video_size 1920x1080 '
            f'-vcodec rawvideo -pix_fmt yuyv422 '
            f'-y "video={device}"'
        )

        info = (
            f"Gerät: {device}\n\n"
            f"FFmpeg-Befehl (wird in separatem Fenster ausgeführt):\n"
            f"{cmd}\n\n"
            "Hinweis: Das Bild wird als Endlosschleife ausgegeben.\n"
            "Fenster schließen zum Stoppen.\n\n"
            "⚠️  Für Ausgabe an physische Capture-Karten (Blackmagic, IEEE 1394)\n"
            "wird ein VirtualCam- oder Loopback-Treiber benötigt\n"
            "(z.B. OBS Virtual Camera, VirtualCam, DirectShow Filter)."
        )
        if messagebox.askyesno("Testbild ausgeben", info + "\n\nJetzt starten?"):
            threading.Thread(
                target=lambda: subprocess.Popen(
                    cmd, shell=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform=="win32" else 0
                ),
                daemon=True
            ).start()
            self._tb_output_status.config(text=f"▶ Ausgabe läuft → {device}")

    # ── Tab 2: Analyse ───────────────────────────────────────────────────────

    def _build_tab_analyse(self):
        f = self._tab_analyse

        tk.Label(f, text="Farbanalyse — Eingangssignal messen", bg="#1e1e1e", fg="white",
                 font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=4,
                 sticky="w", padx=12, pady=(12,4))

        tk.Label(f, text="Quelle:", bg="#1e1e1e", fg="#d4d4d4").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self._src_mode = ttk.Combobox(f, values=["Videodatei / Frame laden", "Live von Capture-Gerät"],
                                       state="readonly", width=32)
        self._src_mode.current(0)
        self._src_mode.grid(row=1, column=1, padx=4, pady=4, sticky="w")

        tk.Label(f, text="Testbild-Typ:", bg="#1e1e1e", fg="#d4d4d4").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self._an_mode = ttk.Combobox(f, values=["EBU 75%", "EBU 100%", "SMPTE RP219", "Macbeth ColorChecker"],
                                      state="readonly", width=32)
        self._an_mode.current(0)
        self._an_mode.grid(row=2, column=1, padx=4, pady=4, sticky="w")

        btn_frame = tk.Frame(f, bg="#1e1e1e")
        btn_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=8, sticky="w")
        tk.Button(btn_frame, text="📂 Frame laden & analysieren", command=self._load_and_analyze,
                  bg="#007acc", fg="white", relief="flat", padx=12, pady=4).pack(side="left", padx=4)
        tk.Button(btn_frame, text="📷 Live-Frame analysieren", command=self._live_analyze,
                  bg="#3c3c3c", fg="white", relief="flat", padx=12, pady=4).pack(side="left", padx=4)

        # Ergebnis-Tabelle
        cols = ("Patch", "Ref R", "Ref G", "Ref B", "Gem R", "Gem G", "Gem B", "ΔR", "ΔG", "ΔB")
        self._tree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=70, anchor="center")
        self._tree.column("Patch", width=130, anchor="w")
        self._tree.grid(row=4, column=0, columnspan=4, padx=10, pady=8, sticky="nsew")

        sb = ttk.Scrollbar(f, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.grid(row=4, column=4, sticky="ns", pady=8)

        self._gamma_label = tk.Label(f, text="Gamma: —", bg="#1e1e1e", fg="#4ec9b0",
                                      font=("Segoe UI", 11))
        self._gamma_label.grid(row=5, column=0, columnspan=4, padx=12, pady=4, sticky="w")

        f.rowconfigure(4, weight=1)
        f.columnconfigure(3, weight=1)

    def _load_and_analyze(self):
        path = filedialog.askopenfilename(
            title="Frame oder Video laden",
            filetypes=[("Bilder & Videos", "*.png *.bmp *.jpg *.tif *.avi *.mov *.mp4 *.mxf"),
                       ("Alle Dateien", "*.*")])
        if not path: return

        ext = Path(path).suffix.lower()
        if ext in (".avi", ".mov", ".mp4", ".mxf", ".mkv"):
            cap = cv2.VideoCapture(path)
            # Frame aus der Mitte
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                messagebox.showerror("Fehler", "Frame konnte nicht gelesen werden.")
                return
        else:
            frame = cv2.imread(path)
            if frame is None:
                messagebox.showerror("Fehler", "Bild konnte nicht geladen werden.")
                return

        self._current_frame = frame
        mode = self._an_mode.get()
        self._run_analysis(frame, mode)

    def _live_analyze(self):
        messagebox.showinfo("Live-Analyse",
            "Live-Analyse: Capture-Gerät als DirectShow-Quelle.\n\n"
            "Aktuell: Bitte zuerst einen Frame als Standbild speichern\n"
            "(z.B. mit OBS → Screenshot) und dann 'Frame laden' nutzen.\n\n"
            "Direktes DirectShow-Capturing folgt in einer späteren Version.")

    def _run_analysis(self, frame, mode=None):
        if mode is None:
            mode = self._an_mode.get()
        if "Macbeth" in mode:
            results = analyze_macbeth_from_frame(frame)
        else:
            results = analyze_bars_from_frame(frame, mode)
        self._analysis_results = results

        # Tabelle befüllen
        for row in self._tree.get_children():
            self._tree.delete(row)

        for (name, ref, meas, delta) in results:
            tag = ""
            if max(abs(d) for d in delta) > 10:
                tag = "warn"
            self._tree.insert("", "end",
                values=(name, *ref, *meas, *delta),
                tags=(tag,))

        self._tree.tag_configure("warn", background="#3a2000", foreground="#ff9900")

        # Gamma schätzen aus Graukeil (falls vorhanden)
        grey = generate_grey_ramp(*frame.shape[1::-1])
        if frame.shape == grey.shape:
            self._gamma = calc_gamma_from_grey_ramp(frame)
        else:
            self._gamma = 1.0
        self._gamma_label.config(text=f"Gamma-Schätzung: {self._gamma:.4f}  (1.0 = linear, >1.0 = zu dunkel)")

        messagebox.showinfo("Analyse abgeschlossen",
            f"✅ {len(results)} Patches analysiert.\n"
            f"Warnungen (|Δ| > 10): {sum(1 for (_,_,_,d) in results if max(abs(x) for x in d)>10)}\n\n"
            "Weiter zu: Tab 'LUT-Generierung'")

    # ── Tab 3: LUT-Generierung ───────────────────────────────────────────────

    def _build_tab_lut(self):
        f = self._tab_lut

        tk.Label(f, text="3D-LUT Generierung", bg="#1e1e1e", fg="white",
                 font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3,
                 sticky="w", padx=12, pady=(12,4))

        tk.Label(f, text="LUT-Auflösung:", bg="#1e1e1e", fg="#d4d4d4").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self._lut_size = ttk.Combobox(f, values=["17 (schnell)", "33 (Standard)", "65 (präzise)"],
                                       state="readonly", width=20)
        self._lut_size.current(1)
        self._lut_size.grid(row=1, column=1, padx=4, pady=4, sticky="w")

        tk.Label(f, text="Gamma-Korrektur:", bg="#1e1e1e", fg="#d4d4d4").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self._lut_gamma_var = tk.StringVar(value="1.0")
        self._lut_gamma_entry = tk.Entry(f, textvariable=self._lut_gamma_var,
                                          bg="#2d2d2d", fg="white", width=8)
        self._lut_gamma_entry.grid(row=2, column=1, padx=4, pady=4, sticky="w")
        tk.Button(f, text="Aus Analyse übernehmen", command=self._adopt_gamma,
                  bg="#3c3c3c", fg="white", relief="flat", padx=8).grid(row=2, column=2, padx=4)

        tk.Label(f, text="Ausgabepfad:", bg="#1e1e1e", fg="#d4d4d4").grid(row=3, column=0, padx=12, pady=4, sticky="w")
        self._lut_outvar = tk.StringVar(value="correction.cube")
        tk.Entry(f, textvariable=self._lut_outvar, bg="#2d2d2d", fg="white", width=40).grid(
            row=3, column=1, padx=4, pady=4, sticky="w")
        tk.Button(f, text="...", command=self._browse_lut_out,
                  bg="#3c3c3c", fg="white", relief="flat").grid(row=3, column=2, padx=4)

        tk.Button(f, text="⚙️ LUT generieren", command=self._generate_lut,
                  bg="#007acc", fg="white", relief="flat", padx=16, pady=6).grid(
                  row=4, column=0, columnspan=3, padx=12, pady=12, sticky="w")

        self._lut_status = tk.Label(f, text="", bg="#1e1e1e", fg="#4ec9b0",
                                     font=("Segoe UI", 11))
        self._lut_status.grid(row=5, column=0, columnspan=3, padx=12, pady=4, sticky="w")

        # Vorschau der Deltas
        self._lut_text = tk.Text(f, bg="#111", fg="#d4d4d4", height=14, font=("Consolas", 9))
        self._lut_text.grid(row=6, column=0, columnspan=3, padx=10, pady=8, sticky="nsew")
        f.rowconfigure(6, weight=1)
        f.columnconfigure(2, weight=1)

    def _adopt_gamma(self):
        self._lut_gamma_var.set(f"{self._gamma:.4f}")

    def _browse_lut_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".cube",
            filetypes=[("LUT-Datei", "*.cube")], title="LUT speichern unter")
        if p: self._lut_outvar.set(p)

    def _generate_lut(self):
        if not self._analysis_results:
            messagebox.showwarning("Keine Daten", "Bitte zuerst eine Analyse durchführen (Tab 'Analyse').")
            return

        size_map = {"17 (schnell)": 17, "33 (Standard)": 33, "65 (präzise)": 65}
        lut_size = size_map.get(self._lut_size.get(), 33)
        gamma = float(self._lut_gamma_var.get())
        out = self._lut_outvar.get()

        def worker():
            path = generate_3dlut(self._analysis_results, gamma, lut_size, out)
            self._lut_path = path
            self.after(0, lambda: self._lut_status.config(
                text=f"✅ LUT gespeichert: {path}  ({lut_size}³ Punkte)"))
            # Zusammenfassung
            summary_lines = [f"3D-LUT Zusammenfassung — {lut_size}³ Punkte\n",
                             f"Gamma: {gamma}\n",
                             f"{'Patch':<20} {'Ref RGB':>18} {'Gem RGB':>18} {'Δ RGB':>18}\n",
                             "-" * 78 + "\n"]
            for (name, ref, meas, delta) in self._analysis_results:
                ok = "⚠️" if max(abs(d) for d in delta) > 10 else "✅"
                summary_lines.append(
                    f"{ok} {name:<18} {str(ref):>18} {str(meas):>18} {str(delta):>18}\n")
            self.after(0, lambda: (
                self._lut_text.delete("1.0", "end"),
                self._lut_text.insert("end", "".join(summary_lines))
            ))

        threading.Thread(target=worker, daemon=True).start()
        self._lut_status.config(text=f"⏳ Generiere LUT ({lut_size}³)…")

    # ── Tab 4: AviSynth-Script ───────────────────────────────────────────────

    def _build_tab_avisynth(self):
        f = self._tab_avisynth

        tk.Label(f, text="AviSynth+ Korrektur-Script", bg="#1e1e1e", fg="white",
                 font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=4,
                 sticky="w", padx=12, pady=(12,4))

        tk.Label(f, text="Capture-Gerät:", bg="#1e1e1e", fg="#d4d4d4").grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self._avs_device = ttk.Combobox(f, values=list(CAPTURE_DEVICES.keys()),
                                         state="readonly", width=38)
        self._avs_device.current(0)
        self._avs_device.grid(row=1, column=1, columnspan=2, padx=4, pady=4, sticky="w")

        tk.Label(f, text="Ausgabedatei:", bg="#1e1e1e", fg="#d4d4d4").grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self._avs_outvar = tk.StringVar(value="output_calibrated.avi")
        tk.Entry(f, textvariable=self._avs_outvar, bg="#2d2d2d", fg="white", width=38).grid(
            row=2, column=1, padx=4, pady=4, sticky="w")
        tk.Button(f, text="...", command=self._browse_avs_out,
                  bg="#3c3c3c", fg="white", relief="flat").grid(row=2, column=3, padx=4)

        tk.Label(f, text="Material:", bg="#1e1e1e", fg="#d4d4d4").grid(row=3, column=0, padx=12, pady=4, sticky="w")
        self._avs_interlaced = tk.BooleanVar(value=True)
        tk.Checkbutton(f, text="Interlaced", variable=self._avs_interlaced,
                       bg="#1e1e1e", fg="#d4d4d4", selectcolor="#3c3c3c",
                       activebackground="#1e1e1e", activeforeground="white").grid(
                       row=3, column=1, padx=4, pady=4, sticky="w")

        self._avs_qtgmc = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="QTGMC Deinterlace vor Encode", variable=self._avs_qtgmc,
                       bg="#1e1e1e", fg="#d4d4d4", selectcolor="#3c3c3c",
                       activebackground="#1e1e1e", activeforeground="white").grid(
                       row=3, column=2, padx=4, pady=4, sticky="w")

        tk.Label(f, text="Encoder-Ausgabe:", bg="#1e1e1e", fg="#d4d4d4").grid(row=4, column=0, padx=12, pady=4, sticky="w")
        self._avs_encoder = ttk.Combobox(f, values=[
            # Lossless / Archiv
            "AVI — unkomprimiert (YUY2)",
            "AVI — FFV1 Lossless",
            "MKV — FFV1 Lossless",
            # Broadcast-Codecs
            "MXF — DVCPro50 (IMX/DVCPRO50 via FFmpeg)",
            "MXF — XDCAM HD422 (50 Mbit, via FFmpeg)",
            "AVI — DV25 (IEC 61834)",
            "AVI — DV50 / DVCPro50",
            # Delivery H.264/H.265
            "MKV — H.264 (x264, CRF 18)",
            "MKV — H.264 (x264, CRF 23 — Web)",
            "MKV — H.265 (x265, CRF 22)",
            "MP4 — H.264 (x264, CRF 18)",
            "MP4 — H.265 (x265, CRF 22)",
            # ProRes (macOS/Cross-Platform)
            "MOV — Apple ProRes 422",
            "MOV — Apple ProRes 422 HQ",
            "MOV — Apple ProRes 4444",
            # DNxHD
            "MXF — DNxHD 185x (1080p25)",
            "MOV — DNxHD 185x (1080p25)",
        ], state="readonly", width=46)
        self._avs_encoder.current(0)
        self._avs_encoder.grid(row=4, column=1, columnspan=2, padx=4, pady=4, sticky="w")

        tk.Button(f, text="📄 Script generieren & speichern", command=self._generate_avs,
                  bg="#007acc", fg="white", relief="flat", padx=16, pady=6).grid(
                  row=5, column=0, columnspan=4, padx=12, pady=10, sticky="w")

        self._avs_text = tk.Text(f, bg="#111", fg="#9cdcfe", height=18,
                                  font=("Consolas", 9))
        self._avs_text.grid(row=6, column=0, columnspan=4, padx=10, pady=8, sticky="nsew")
        f.rowconfigure(6, weight=1)
        f.columnconfigure(3, weight=1)

    def _browse_avs_out(self):
        p = filedialog.asksaveasfilename(defaultextension=".avi",
            filetypes=[("AVI", "*.avi"), ("MKV", "*.mkv")], title="Ausgabedatei")
        if p: self._avs_outvar.set(p)

    def _build_ffmpeg_cmd(self, avs_path, out_base, enc, interlaced_out):
        """Gibt den passenden FFmpeg-Befehl als Kommentar-String zurück."""
        i_flag = "-flags +ildct+ilme -top 1 " if interlaced_out else ""

        # Ausgabe-Extension anpassen
        def out(ext): return str(Path(out_base).with_suffix(ext))

        lines = ["\n\n# ═══ FFmpeg Encode-Befehl ═══"]

        if "unkomprimiert" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v rawvideo -pix_fmt yuyv422 "{out(".avi")}"')

        elif "FFV1" in enc and "AVI" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v ffv1 -level 3 "{out(".avi")}"')

        elif "FFV1" in enc and "MKV" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v ffv1 -level 3 "{out(".mkv")}"')

        elif "DVCPro50" in enc or "DV50" in enc:
            lines += [
                f'# DVCPro50 / DV50 — 50 Mbit/s, 4:2:2',
                f'# ffmpeg -i "{avs_path}" -c:v dvvideo -pix_fmt yuv422p {i_flag}"{out(".avi")}"',
                f'# Für MXF-Wrapping:',
                f'# ffmpeg -i "{avs_path}" -c:v dvvideo -pix_fmt yuv422p -f mxf "{out(".mxf")}"',
            ]

        elif "DV25" in enc:
            lines += [
                f'# DV25 — 25 Mbit/s, 4:1:1 (NTSC) / 4:2:0 (PAL)',
                f'# ffmpeg -i "{avs_path}" -c:v dvvideo -pix_fmt yuv420p {i_flag}"{out(".avi")}"',
            ]

        elif "XDCAM" in enc:
            lines += [
                f'# XDCAM HD422 — 50 Mbit/s, 4:2:2, 1080i',
                f'# ffmpeg -i "{avs_path}" -c:v mpeg2video -b:v 50M -pix_fmt yuv422p \\',
                f'#   -dc 10 -intra_vlc 1 -non_linear_quant 1 -qscale:v 1 \\',
                f'#   {i_flag}-f mxf_opatom "{out(".mxf")}"',
            ]

        elif "H.264" in enc and "CRF 18" in enc and "MKV" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v libx264 -crf 18 -preset slow {i_flag}"{out(".mkv")}"')

        elif "H.264" in enc and "CRF 23" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v libx264 -crf 23 -preset medium {i_flag}"{out(".mkv")}"')

        elif "H.264" in enc and "MP4" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v libx264 -crf 18 -preset slow -movflags +faststart "{out(".mp4")}"')

        elif "H.265" in enc and "MKV" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v libx265 -crf 22 -preset slow {i_flag}"{out(".mkv")}"')

        elif "H.265" in enc and "MP4" in enc:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v libx265 -crf 22 -preset slow -movflags +faststart "{out(".mp4")}"')

        elif "ProRes 422 HQ" in enc:
            lines += [
                f'# Apple ProRes 422 HQ',
                f'# ffmpeg -i "{avs_path}" -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le "{out(".mov")}"',
            ]

        elif "ProRes 4444" in enc:
            lines += [
                f'# Apple ProRes 4444',
                f'# ffmpeg -i "{avs_path}" -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le "{out(".mov")}"',
            ]

        elif "ProRes 422" in enc:
            lines += [
                f'# Apple ProRes 422',
                f'# ffmpeg -i "{avs_path}" -c:v prores_ks -profile:v 2 -pix_fmt yuv422p10le "{out(".mov")}"',
            ]

        elif "DNxHD" in enc and "MXF" in enc:
            lines += [
                f'# DNxHD 185x — 1080p25 / 1080i25',
                f'# ffmpeg -i "{avs_path}" -c:v dnxhd -b:v 185M -pix_fmt yuv422p {i_flag}-f mxf "{out(".mxf")}"',
            ]

        elif "DNxHD" in enc and "MOV" in enc:
            lines += [
                f'# DNxHD 185x — 1080p25 / 1080i25',
                f'# ffmpeg -i "{avs_path}" -c:v dnxhd -b:v 185M -pix_fmt yuv422p {i_flag}"{out(".mov")}"',
            ]

        else:
            lines.append(f'# ffmpeg -i "{avs_path}" -c:v ffv1 "{out(".mkv")}"')

        if interlaced_out:
            lines.append("# Hinweis: Interlaced-Flags aktiv (-flags +ildct+ilme -top 1)")

        return "\n".join(lines)

    def _generate_avs(self):
        lut = self._lut_path or "correction.cube"
        out = self._avs_outvar.get()
        device = self._avs_device.get()
        interlaced = self._avs_interlaced.get()
        qtgmc = self._avs_qtgmc.get()
        gamma = float(self._lut_gamma_var.get()) if hasattr(self, '_lut_gamma_var') else self._gamma

        avs_path, script = generate_avisynth_script(
            device, lut, out, gamma, interlaced, qtgmc)

        self._avs_text.delete("1.0", "end")
        self._avs_text.insert("end", script)

        # Encoder-Hinweis anhängen
        enc = self._avs_encoder.get()
        hint = self._build_ffmpeg_cmd(avs_path, out, enc, interlaced and not qtgmc)
        self._avs_text.insert("end", hint)

        messagebox.showinfo("Script gespeichert", f"AviSynth-Script gespeichert:\n{avs_path}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = VidCal()
    app.mainloop()
