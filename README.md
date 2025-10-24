# Simple DICOM Series Viewer

This is a small educational DICOM (CT/MRI) series viewer implemented in Python using PySimpleGUI.

Features:

- Load a folder of DICOM files and stack into a 3D volume
- Slice slider, Prev/Next buttons
- Window/Level (center/width) adjustment
- Save slice as PNG

Requirements

- Python 3.8+
- See `requirements.txt` to install packages:

```
pip install -r requirements.txt
```

Run

```
python image.py [PATH_TO_DICOM_FOLDER]
```

When run without an argument, open the GUI and use "Open Folder" to select a DICOM folder.

Notes

- The viewer is intentionally minimal for teaching. It supports modality LUT and basic window/level.
- If folder contains non-DICOM files they are ignored.
