# VidCal 🎨 — Video Calibration Tool

Professionelles Kalibrierungstool für Videorecorder-Eingangssignale.  
Analyse via EBU/SMPTE Colour Charts → LUT-Generierung → AviSynth+ Korrektur.

## Features

- **Testbild-Generator** — EBU Bars 75%/100%, SMPTE RP219, Graukeil (16/32 Stufen)
- **Farbanalyse** — Automatische Patch-Erkennung, Soll-/Ist-Vergleich, Delta RGB
- **Gamma-Analyse** — Automatische Gamma-Schätzung aus Graukeil
- **3D-LUT Generierung** — `.cube` Format (17³ / 33³ / 65³), kompatibel mit FFmpeg & AviSynth+
- **AviSynth+ Script-Generator** — Automatisches Korrektur-Script für alle Capture-Geräte
- **Interlaced-Support** — mit optionalem QTGMC-Deinterlace

## Unterstützte Capture-Geräte

| Gerät | Typ |
|---|---|
| Blackmagic UltraStudio Mini Recorder | PCIe / Thunderbolt |
| Blackmagic Intensity 4K | PCIe |
| I/O Data GV-USB2 | USB |
| Elgato Cam Link 4K | USB |
| Generic VfW / DirectShow | Universell |

## Workflow

```
1. Testbild-Generator  →  EBU/SMPTE Bars als PNG exportieren
2. Bars auf Band einspielen (oder direkt von Recorder aufnehmen)
3. Frame laden & analysieren  →  Delta-Tabelle + Gamma
4. 3D-LUT generieren  →  correction.cube
5. AviSynth+ Script generieren  →  Korrigiertes Signal aufnehmen
```

## Abhängigkeiten

```
pip install opencv-python Pillow numpy scipy
```

AviSynth+ (systemweit installiert) für die Script-Ausgabe.

## Ausgabeformate

- **AVI** (unkomprimiert / FFV1) — Archiv/Mezzanin
- **MKV + H.264** (x264) — Delivery
- **MKV + H.265** (x265) — Delivery kompakt
- Interlaced: natives Interlaced oder QTGMC-Deinterlace vor Encode
