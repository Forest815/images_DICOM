#!/usr/bin/env python3
"""
Simple DICOM series viewer (CT/MRI) using PySimpleGUI.

Features:
- Open a folder containing a DICOM series
- Stack slices into a 3D volume (sorted by ImagePositionPatient z or InstanceNumber)
- Slice slider to navigate axial slices
- Window/Level (center/width) controls
- Next/Prev buttons

Usage:
    python image.py [PATH_TO_DICOM_FOLDER]

This is intentionally a lightweight viewer for educational use.
"""
import os
import sys
import io
from typing import List, Tuple, Optional

try:
    import pydicom
    from pydicom.pixel_data_handlers.util import apply_modality_lut
    import numpy as np
    from PIL import Image, ImageDraw
    try:
        import PySimpleGUI as sg
    except Exception:
        sg = None
except Exception as e:
    print("Missing dependency:", e)
    print("Please install requirements from requirements.txt")
    raise


# --- 変更: デフォルトで読み込む DICOM フォルダを指定 (必要に応じてパスを変更してください) ---
DEFAULT_DICOM_FOLDER = r"c:\Users\kazus\Documents\4th\images\2025-知能情報実験実習2用画像データ\TEST_ANON44302_CT_2011-04-15_000000_._T=0%,PR=97%.-).2%,AR(cm)=1.15.-).1.53..SBRT.4DCT.2.5mm__n140__84634"



def load_dicom_series(folder: str) -> Tuple[np.ndarray, dict]:
    """Load DICOM files from folder and return a 3D numpy array (z,y,x) and metadata.

    Only files that contain PixelData are considered. Slices are sorted by
    ImagePositionPatient (z) if available, otherwise by InstanceNumber.
    """
    files = []
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=False, force=True)
        except Exception:
            continue
        if hasattr(ds, 'PixelData'):
            files.append((path, ds))

    if not files:
        raise RuntimeError("No DICOM files with pixel data found in folder: %s" % folder)

    # Sort
    def sort_key(item):
        ds = item[1]
        if hasattr(ds, 'ImagePositionPatient'):
            try:
                return float(ds.ImagePositionPatient[2])
            except Exception:
                pass
        if hasattr(ds, 'InstanceNumber'):
            try:
                return int(ds.InstanceNumber)
            except Exception:
                pass
        return item[0]

    files.sort(key=sort_key)

    slices = []
    for path, ds in files:
        try:
            arr = ds.pixel_array
        except Exception:
            # skip unreadable
            continue
        # apply modality LUT (rescale) if present
        try:
            arr = apply_modality_lut(arr, ds)
        except Exception:
            pass
        slices.append((arr, ds))

    if not slices:
        raise RuntimeError("No readable image slices in folder: %s" % folder)

    volume = np.stack([s[0] for s in slices], axis=0).astype(np.float32)

    # metadata: try to get default window/level from first slice
    meta = {}
    first_ds = slices[0][1]
    if hasattr(first_ds, 'WindowCenter') and hasattr(first_ds, 'WindowWidth'):
        try:
            wc = first_ds.WindowCenter
            ww = first_ds.WindowWidth
            # may be sequences
            if isinstance(wc, pydicom.multival.MultiValue):
                wc = float(wc[0])
            if isinstance(ww, pydicom.multival.MultiValue):
                ww = float(ww[0])
            meta['window_center'] = float(wc)
            meta['window_width'] = float(ww)
        except Exception:
            pass

    # Fallback center/width from image stats
    if 'window_center' not in meta:
        meta['window_center'] = float(np.median(volume))
    if 'window_width' not in meta:
        meta['window_width'] = float(np.percentile(volume, 99) - np.percentile(volume, 1))

    # store pixel spacing if available
    try:
        meta['pixel_spacing'] = getattr(first_ds, 'PixelSpacing', None)
        meta['slice_thickness'] = getattr(first_ds, 'SliceThickness', None)
    except Exception:
        pass

    # store patient info if available
    try:
        pn = getattr(first_ds, 'PatientName', None)
        if pn is not None:
            # pydicom may return PersonName type; convert to str
            meta['patient_name'] = str(pn)
        pid = getattr(first_ds, 'PatientID', None)
        if pid is not None:
            meta['patient_id'] = str(pid)
    except Exception:
        pass

    return volume, meta


def apply_window_level(slice_img: np.ndarray, center: float, width: float) -> np.ndarray:
    """Apply window/level to a single 2D slice and return uint8 image (0-255)."""
    if width <= 0:
        width = 1.0
    low = center - (width / 2.0)
    high = center + (width / 2.0)
    clipped = np.clip(slice_img, low, high)
    norm = (clipped - low) / (high - low)
    img8 = (norm * 255.0).astype(np.uint8)
    return img8


def get_oriented_slice(volume: np.ndarray, view: str, index: int) -> np.ndarray:
    """Return a 2D numpy array for given view and index.

    view: 'Axial' (default) -> slices along z (volume[index,:,:])
          'Coronal'       -> slices along y (volume[:,index,:]) -> returned as (z,x) but we transpose to (x,z) for display
          'Sagittal'      -> slices along x (volume[:,:,index]) -> returned as (z,y) but we transpose to (y,z) for display
    The transposes ensure a visually intuitive orientation (rows/cols) for display.
    """
    v = view.lower()
    if v.startswith('a') or v == 'axial':
        # shape (Z, H, W) -> (H, W)
        return volume[int(index)]
    elif v.startswith('c') or v == 'coronal':
        # coronal: slice along Y -> arr shape (Z, W)
        # return as (Z, W) so rows = slices (depth), cols = x direction
        arr = volume[:, int(index), :]
        return arr
    elif v.startswith('s') or v == 'sagittal':
        # sagittal: slice along X -> arr shape (Z, H)
        # transpose to (H, Z) so rows = y direction, cols = slices (depth)
        arr = volume[:, :, int(index)]
        return np.transpose(arr, (1, 0))
    else:
        return volume[int(index)]


def pil_image_bytes_from_array(img8: np.ndarray) -> bytes:
    pil = Image.fromarray(img8)
    bio = io.BytesIO()
    pil.save(bio, format='PNG')
    return bio.getvalue()


def pil_bytes_from(obj) -> bytes:
    """Accept a PIL Image or numpy array and return PNG bytes."""
    if isinstance(obj, Image.Image):
        pil = obj
    else:
        pil = Image.fromarray(obj)
    bio = io.BytesIO()
    pil.save(bio, format='PNG')
    return bio.getvalue()


def overlay_crosshairs(axial, coronal, sagittal, cross_info):
    """Given three 2D numpy arrays and cross_info (x,y,z), return PIL images with crosshair overlays.
    axial: (H,W), coronal: (Z,W), sagittal: (H,Z)
    cross_info: (x, y, z) where x is column, y is row, z is axial index
    """
    x, y, z = cross_info
    # Axial: draw vertical at x, horizontal at y
    p_ax = Image.fromarray(axial).convert('RGB')
    draw = ImageDraw.Draw(p_ax)
    W = p_ax.width; H = p_ax.height
    if 0 <= x < W:
        draw.line([(x, 0), (x, H)], fill=(255,0,0), width=1)
    if 0 <= y < H:
        draw.line([(0, y), (W, y)], fill=(255,0,0), width=1)

    # Coronal: shape (Z,W) -> draw vertical at x, horizontal at z
    p_cor = Image.fromarray(coronal).convert('RGB')
    drawc = ImageDraw.Draw(p_cor)
    Wc = p_cor.width; Hc = p_cor.height
    if 0 <= x < Wc:
        drawc.line([(x, 0), (x, Hc)], fill=(255,0,0), width=1)
    if 0 <= z < Hc:
        drawc.line([(0, z), (Wc, z)], fill=(255,0,0), width=1)

    # Sagittal: shape (H,Z) -> draw vertical at z, horizontal at y
    p_sag = Image.fromarray(sagittal).convert('RGB')
    draws = ImageDraw.Draw(p_sag)
    Ws = p_sag.width; Hs = p_sag.height
    if 0 <= z < Ws:
        draws.line([(z, 0), (z, Hs)], fill=(255,0,0), width=1)
    if 0 <= y < Hs:
        draws.line([(0, y), (Ws, y)], fill=(255,0,0), width=1)

    return p_ax, p_cor, p_sag


def normalize_display_image(img8: np.ndarray, target_shape: Tuple[int,int], view: str) -> np.ndarray:
    """Take a uint8 2D image (img8), rotate if needed, and resize to target_shape (H,W).

    img8: uint8 numpy array
    target_shape: (H, W)
    view: 'Axial','Coronal','Sagittal' (rotate sagittal CCW 90deg)
    Returns uint8 numpy array of shape (H,W).
    """
    H, W = target_shape
    pil = Image.fromarray(img8)
    v = view.lower()
    if v.startswith('s') or v == 'sagittal':
        # rotate counter-clockwise 90 degrees
        pil = pil.rotate(90, expand=True)
    elif v.startswith('c') or v == 'coronal':
        # flip coronal vertically (上下反転)
        pil = pil.transpose(Image.FLIP_TOP_BOTTOM)

    arr = np.array(pil)
    # ensure 2D grayscale
    if arr.ndim == 3:
        # convert RGB to luminance if needed
        arr = np.array(Image.fromarray(arr).convert('L'))

    h, w = arr.shape
    # create black canvas of target size
    out = np.zeros((H, W), dtype=np.uint8)

    # source crop coords (if source larger than target, crop center)
    src_y0 = max(0, (h - H) // 2)
    src_x0 = max(0, (w - W) // 2)
    src_y1 = src_y0 + min(h, H)
    src_x1 = src_x0 + min(w, W)

    # destination coords (centered)
    dst_y0 = max(0, (H - h) // 2)
    dst_x0 = max(0, (W - w) // 2)
    dst_y1 = dst_y0 + (src_y1 - src_y0)
    dst_x1 = dst_x0 + (src_x1 - src_x0)

    out[dst_y0:dst_y1, dst_x0:dst_x1] = arr[src_y0:src_y1, src_x0:src_x1]
    return out



def run_gui_sg(initial_folder: Optional[str] = None):
    try:
        sg.theme('DarkBlue3')
    except Exception:
        # Some PySimpleGUI installs (placeholder packages) may not expose theme; continue without setting theme
        pass

    # Left controls
    layout_col = [
        [sg.Text('DICOM Series Viewer', font=('Any', 16))],
        [sg.Text('', key='-PATIENT-', size=(60,1))],
        [sg.Button('Open Folder'), sg.Input(initial_folder or '', key='-FOLDER-', enable_events=True, size=(40,1)), sg.Button('Reload')],
        [sg.Text('View'), sg.Combo(['Axial','Coronal','Sagittal','Multi'], default_value='Axial', key='-VIEW-', enable_events=True)],
        [sg.Text('Slice:'), sg.Slider(range=(0,1), orientation='h', size=(60,15), key='-SLICE-', enable_events=True)],
        [sg.Text('Window Center'), sg.Slider(range=( -2000, 2000), orientation='h', size=(40,12), key='-WC-', enable_events=True)],
        [sg.Text('Window Width'), sg.Slider(range=(1, 4000), orientation='h', size=(40,12), key='-WW-', enable_events=True)],
        [sg.Button('Prev'), sg.Button('Next'), sg.Button('Save Slice'), sg.Button('Quit')]
    ]

    # Image panes: Axial | Coronal | Sagittal
    image_col = [
        [sg.Image(key='-AXIAL-', size=(512,512)), sg.Image(key='-CORONAL-', size=(512,512)), sg.Image(key='-SAGITTAL-', size=(512,512))]
    ]

    layout = [[sg.Column(layout_col), sg.VSeparator(), sg.Column(image_col)]]

    window = sg.Window('DICOM Viewer', layout, resizable=True, finalize=True)

    volume = None
    meta = {}
    current_slice = 0
    cross_pos = None  # (x,y) in axial coords

    # 初期フォルダが指定されていれば自動読み込みする
    start_folder = initial_folder if initial_folder is not None else DEFAULT_DICOM_FOLDER
    if start_folder and os.path.isdir(start_folder):
        window['-FOLDER-'].update(start_folder)
        try:
            volume, meta = load_dicom_series(start_folder)
            current_slice = 0
            # update patient label
            pname = meta.get('patient_name') or 'Unknown'
            pid = meta.get('patient_id') or 'Unknown'
            window['-PATIENT-'].update(f"Patient: {pname}    ID: {pid}")
            window['-SLICE-'].update(range=(0, max(0, volume.shape[0]-1)), value=0)
            wc = int(meta.get('window_center', 0))
            ww = int(max(1, meta.get('window_width', 1)))
            window['-WC-'].update(range=(-2000,2000), value=wc)
            window['-WW-'].update(range=(1,4000), value=ww)
            # initial image
            def _init_update():
                nonlocal current_slice
                if volume is None:
                    return
                img8 = apply_window_level(volume[current_slice], wc, ww)
                window['-IMAGE-'].update(data=pil_image_bytes_from_array(img8))
            _init_update()
        except Exception as e:
            sg.popup_error('Failed to load initial DICOM folder', e)

    def render_panes(ax_idx=None, cor_idx=None, sag_idx=None):
        # Render all three panes using provided indices (fallback to center indices)
        if volume is None:
            window['-AXIAL-'].update(data=b'')
            window['-CORONAL-'].update(data=b'')
            window['-SAGITTAL-'].update(data=b'')
            return
        Z, H, W = volume.shape
        if ax_idx is None:
            ax_idx = int(np.clip(current_slice, 0, Z-1))
        if cor_idx is None:
            cor_idx = int(np.clip(H//2, 0, H-1))
        if sag_idx is None:
            sag_idx = int(np.clip(W//2, 0, W-1))

        center = float(window['-WC-'].get()) if window['-WC-'].get() is not None else meta.get('window_center', 0)
        width = float(window['-WW-'].get()) if window['-WW-'].get() is not None else meta.get('window_width', 1)

        axial = apply_window_level(get_oriented_slice(volume, 'Axial', ax_idx), center, width)
        coronal = apply_window_level(get_oriented_slice(volume, 'Coronal', cor_idx), center, width)
        sagittal = apply_window_level(get_oriented_slice(volume, 'Sagittal', sag_idx), center, width)

        target = (H, W)
        ax_disp = normalize_display_image(axial, target, 'Axial')
        cor_disp = normalize_display_image(coronal, target, 'Coronal')
        sag_disp = normalize_display_image(sagittal, target, 'Sagittal')

        # if crosshair present, overlay
        if cross_pos is not None:
            cx, cy, cz = cross_pos
            p_ax, p_cor, p_sag = overlay_crosshairs(ax_disp, cor_disp, sag_disp, (cx, cy, cz))
            window['-AXIAL-'].update(data=pil_bytes_from(p_ax))
            window['-CORONAL-'].update(data=pil_bytes_from(p_cor))
            window['-SAGITTAL-'].update(data=pil_bytes_from(p_sag))
        else:
            window['-AXIAL-'].update(data=pil_image_bytes_from_array(ax_disp))
            window['-CORONAL-'].update(data=pil_image_bytes_from_array(cor_disp))
            window['-SAGITTAL-'].update(data=pil_image_bytes_from_array(sag_disp))
        window['-SLICE-'].update(value=ax_idx)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == 'Quit':
            break

        if event == 'Open Folder':
            folder = sg.popup_get_folder('Select folder containing DICOM files', default_path=values.get('-FOLDER-') or '.', no_window=True)
            if folder:
                window['-FOLDER-'].update(folder)
                try:
                    volume, meta = load_dicom_series(folder)
                    current_slice = 0
                    # set slider ranges depending on view
                    view_val = window['-VIEW-'].get() if window['-VIEW-'].get() is not None else 'Axial'
                    if view_val == 'Axial':
                        count = volume.shape[0]
                    elif view_val == 'Coronal':
                        count = volume.shape[1]
                    else:
                        count = volume.shape[2]
                    window['-SLICE-'].update(range=(0, max(0, count-1)), value=0)
                    # update patient label
                    pname = meta.get('patient_name') or 'Unknown'
                    pid = meta.get('patient_id') or 'Unknown'
                    window['-PATIENT-'].update(f"Patient: {pname}    ID: {pid}")
                    # set WL sliders initial
                    wc = int(meta.get('window_center', 0))
                    ww = int(max(1, meta.get('window_width', 1)))
                    # clamp to slider ranges
                    window['-WC-'].update(range=(-2000,2000), value=wc)
                    window['-WW-'].update(range=(1,4000), value=ww)
                    render_panes()
                except Exception as e:
                    sg.popup_error('Failed to load DICOM series', e)

        # handle mouse events for PySimpleGUI images (Right-drag WL, Left-click crosshair)
        if isinstance(event, tuple) and event[0].startswith('-AXIAL-'):
            # event like ('-AXIAL-', '+UP', x, y) or ('-AXIAL-', '+DOWN', x, y) or ('-AXIAL-', 'MOTION', x, y)
            # Simplify: handle left click down/up and right drag
            elem, etype, mx, my = event
            # left click: set crosshair in axial coordinates
            if etype == '+UP':
                try:
                    mx = int(mx); my = int(my)
                    # map mouse coords to image coords roughly (images are displayed same size as target)
                    # assume displayed image equals target (H,W)
                    cx = mx; cy = my; cz = int(current_slice)
                    cross_pos = (cx, cy, cz)
                    render_panes()
                except Exception:
                    pass

        if event == '-VIEW-':
            # when view changes, adjust slider range and refresh
            if volume is not None:
                view_val = values.get('-VIEW-') or 'Axial'
                if view_val == 'Axial':
                    count = volume.shape[0]
                elif view_val == 'Coronal':
                    count = volume.shape[1]
                else:
                    count = volume.shape[2]
                window['-SLICE-'].update(range=(0, max(0, count-1)), value=min(current_slice, max(0, count-1)))
                render_panes()

        elif event == 'Reload':
            folder = values.get('-FOLDER-')
            if folder:
                try:
                    volume, meta = load_dicom_series(folder)
                    current_slice = 0
                    window['-SLICE-'].update(range=(0, max(0, volume.shape[0]-1)), value=0)
                    wc = int(meta.get('window_center', 0))
                    ww = int(max(1, meta.get('window_width', 1)))
                    window['-WC-'].update(value=wc)
                    window['-WW-'].update(value=ww)
                    # update patient label
                    pname = meta.get('patient_name', '')
                    pid = meta.get('patient_id', '')
                    if pname or pid:
                        window['-PATIENT-'].update(f"Patient: {pname}    ID: {pid}")
                    render_panes()
                except Exception as e:
                    sg.popup_error('Reload failed', e)

        elif event == '-SLICE-':
            if volume is not None:
                current_slice = int(values['-SLICE-'])
                render_panes()

        elif event == '-WC-' or event == '-WW-':
            if volume is not None:
                render_panes()

        elif event == 'Prev':
            if volume is not None:
                # decrement within current view range
                view_val = window['-VIEW-'].get() if window['-VIEW-'].get() is not None else 'Axial'
                if view_val == 'Axial':
                    max_idx = volume.shape[0]-1
                elif view_val == 'Coronal':
                    max_idx = volume.shape[1]-1
                else:
                    max_idx = volume.shape[2]-1
                current_slice = max(0, current_slice - 1)
                render_panes()

        elif event == 'Next':
            if volume is not None:
                view_val = window['-VIEW-'].get() if window['-VIEW-'].get() is not None else 'Axial'
                if view_val == 'Axial':
                    max_idx = volume.shape[0]-1
                elif view_val == 'Coronal':
                    max_idx = volume.shape[1]-1
                else:
                    max_idx = volume.shape[2]-1
                current_slice = min(max_idx, current_slice + 1)
                render_panes()

        elif event == 'Save Slice':
            if volume is None:
                continue
            fname = sg.popup_get_file('Save current slice as PNG', save_as=True, no_window=True, file_types=(('PNG','*.png'),))
            if fname:
                view_val = window['-VIEW-'].get() if window['-VIEW-'].get() is not None else 'Axial'
                slice_img = get_oriented_slice(volume, view_val, current_slice)
                img8 = apply_window_level(slice_img, float(window['-WC-'].get()), float(window['-WW-'].get()))
                # normalize before saving
                target_shape = (volume.shape[1], volume.shape[2])
                outimg = normalize_display_image(img8, target_shape, view_val)
                Image.fromarray(outimg).save(fname)
                sg.popup('Saved', fname)

    window.close()


def run_gui_tkinter(initial_folder: Optional[str] = None):
    # Minimal tkinter-based fallback GUI (avoids PySimpleGUI dependency issues)
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
        from PIL import ImageTk
    except Exception as e:
        print('tkinter fallback not available:', e)
        raise

    root = tk.Tk()
    root.title('DICOM Viewer (tkinter)')

    # state
    volume = None
    meta = {}
    current_slice = 0

    # three panels using Labels
    axial_label = tk.Label(root)
    axial_label.pack(side=tk.RIGHT, expand=True)
    coronal_label = tk.Label(root)
    coronal_label.pack(side=tk.RIGHT, expand=True)
    sagittal_label = tk.Label(root)
    sagittal_label.pack(side=tk.RIGHT, expand=True)

    ctrl_frame = tk.Frame(root)
    ctrl_frame.pack(side=tk.LEFT, fill=tk.Y)

    folder_var = tk.StringVar(value=initial_folder or DEFAULT_DICOM_FOLDER)

    view_var = tk.StringVar(value='Axial')
    # patient info label
    patient_label = tk.Label(ctrl_frame, text='')
    patient_label.pack(fill=tk.X)

    # state for crosshair and WL interaction
    tk_cross = None
    tk_wc = None
    tk_ww = None

    def load_folder(folder):
        nonlocal volume, meta, current_slice
        try:
            volume, meta = load_dicom_series(folder)
        except Exception as e:
            messagebox.showerror('Error', f'Failed to load DICOM series:\n{e}')
            return
        current_slice = 0
        # update patient label (display 'Unknown' if missing)
        pname = meta.get('patient_name') or 'Unknown'
        pid = meta.get('patient_id') or 'Unknown'
        patient_label.config(text=f"Patient: {pname}    ID: {pid}")
        # set slice range based on view
        if view_var.get() == 'Axial':
            slice_scale.config(to=max(0, volume.shape[0]-1))
        elif view_var.get() == 'Coronal':
            slice_scale.config(to=max(0, volume.shape[1]-1))
        else:
            slice_scale.config(to=max(0, volume.shape[2]-1))
        wc = int(meta.get('window_center', 0))
        ww = int(max(1, meta.get('window_width', 1)))
        wc_scale.set(wc)
        ww_scale.set(ww)
        # set defaults for tk interaction
        nonlocal tk_wc, tk_ww
        tk_wc = wc
        tk_ww = ww
        update_image()

    def on_open():
        d = filedialog.askdirectory(initialdir=folder_var.get() or '.')
        if d:
            folder_var.set(d)
            load_folder(d)

    def update_image():
        nonlocal current_slice
        if volume is None:
            axial_label.config(image='')
            coronal_label.config(image='')
            sagittal_label.config(image='')
            return
        current_slice = int(slice_scale.get())
        center = float(wc_scale.get())
        width = float(ww_scale.get())
        view_name = view_var.get()
        img8 = apply_window_level(get_oriented_slice(volume, view_name, current_slice), center, width)
        # normalize to axial target shape
        target_shape = (volume.shape[1], volume.shape[2])
        disp = normalize_display_image(img8, target_shape, view_name)
        # render into the three panels
        Z, H, W = volume.shape
        ax = apply_window_level(get_oriented_slice(volume, 'Axial', current_slice), center, width)
        cor = apply_window_level(get_oriented_slice(volume, 'Coronal', int(slice_scale.get() if view_name=='Coronal' else H//2)), center, width)
        sag = apply_window_level(get_oriented_slice(volume, 'Sagittal', int(slice_scale.get() if view_name=='Sagittal' else W//2)), center, width)
        target = (H, W)
        axd = normalize_display_image(ax, target, 'Axial')
        cord = normalize_display_image(cor, target, 'Coronal')
        sagd = normalize_display_image(sag, target, 'Sagittal')
        # overlay crosshair if present
        if tk_cross is not None:
            pax, pco, psa = overlay_crosshairs(axd, cord, sagd, tk_cross)
            ax_pil = pax
            co_pil = pco
            sa_pil = psa
        else:
            ax_pil = Image.fromarray(axd)
            co_pil = Image.fromarray(cord)
            sa_pil = Image.fromarray(sagd)
        a_tk = ImageTk.PhotoImage(ax_pil)
        c_tk = ImageTk.PhotoImage(co_pil)
        s_tk = ImageTk.PhotoImage(sa_pil)
        axial_label.image = a_tk; axial_label.config(image=a_tk)
        coronal_label.image = c_tk; coronal_label.config(image=c_tk)
        sagittal_label.image = s_tk; sagittal_label.config(image=s_tk)

    def on_prev():
        slice_scale.set(max(0, slice_scale.get() - 1))
        update_image()

    def on_next():
        slice_scale.set(min(slice_scale['to'], slice_scale.get() + 1))
        update_image()

    def on_save():
        if volume is None:
            return
        fname = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG','*.png')])
        if fname:
            view_name = view_var.get()
            img8 = apply_window_level(get_oriented_slice(volume, view_name, int(slice_scale.get())), float(wc_scale.get()), float(ww_scale.get()))
            target_shape = (volume.shape[1], volume.shape[2])
            outimg = normalize_display_image(img8, target_shape, view_name)
            Image.fromarray(outimg).save(fname)
            messagebox.showinfo('Saved', fname)

    tk.Button(ctrl_frame, text='Open Folder', command=on_open).pack(fill=tk.X)
    tk.Button(ctrl_frame, text='Load Default', command=lambda: load_folder(folder_var.get())).pack(fill=tk.X)
    tk.Label(ctrl_frame, text='View').pack()
    def on_view_change(v):
        # adjust slice range based on selected view
        if volume is None:
            return
        if v == 'Axial':
            slice_scale.config(to=max(0, volume.shape[0]-1))
        elif v == 'Coronal':
            slice_scale.config(to=max(0, volume.shape[1]-1))
        else:
            slice_scale.config(to=max(0, volume.shape[2]-1))
        update_image()

    tk.OptionMenu(ctrl_frame, view_var, 'Axial', 'Coronal', 'Sagittal', command=on_view_change).pack(fill=tk.X)

    slice_scale = tk.Scale(ctrl_frame, from_=0, to=0, orient=tk.HORIZONTAL, label='Slice', command=lambda v: update_image())
    slice_scale.pack(fill=tk.X)

    wc_scale = tk.Scale(ctrl_frame, from_=-2000, to=2000, orient=tk.HORIZONTAL, label='Window Center', command=lambda v: update_image())
    wc_scale.pack(fill=tk.X)
    ww_scale = tk.Scale(ctrl_frame, from_=1, to=4000, orient=tk.HORIZONTAL, label='Window Width', command=lambda v: update_image())
    ww_scale.pack(fill=tk.X)

    btn_frame = tk.Frame(ctrl_frame)
    btn_frame.pack(fill=tk.X)
    tk.Button(btn_frame, text='Prev', command=on_prev).pack(side=tk.LEFT, expand=True, fill=tk.X)
    tk.Button(btn_frame, text='Next', command=on_next).pack(side=tk.LEFT, expand=True, fill=tk.X)
    tk.Button(btn_frame, text='Save Slice', command=on_save).pack(side=tk.LEFT, expand=True, fill=tk.X)
    tk.Button(btn_frame, text='Quit', command=root.destroy).pack(side=tk.LEFT, expand=True, fill=tk.X)

    # try auto-load
    start_folder = initial_folder if initial_folder is not None else DEFAULT_DICOM_FOLDER
    if start_folder and os.path.isdir(start_folder):
        load_folder(start_folder)

    # bind mouse: left-click to set crosshair, right-drag to adjust WL
    def tk_on_click(event, panel='axial'):
        nonlocal tk_cross
        # map event.x/y directly
        x, y = event.x, event.y
        # convert to axial coords roughly
        tk_cross = (x, y, current_slice)
        update_image()

    def tk_on_right_drag(event):
        # adjust wc/ww based on motion
        nonlocal tk_wc, tk_ww
        # simple mapping: vertical changes center, horizontal changes width
        dx = event.x
        dy = event.y
        try:
            new_wc = int(wc_scale.get() - dy)
            new_ww = int(max(1, ww_scale.get() + dx))
            wc_scale.set(new_wc)
            ww_scale.set(new_ww)
            update_image()
        except Exception:
            pass

    axial_label.bind('<Button-1>', lambda e: tk_on_click(e, 'axial'))
    coronal_label.bind('<Button-1>', lambda e: tk_on_click(e, 'coronal'))
    sagittal_label.bind('<Button-1>', lambda e: tk_on_click(e, 'sagittal'))
    axial_label.bind('<B3-Motion>', tk_on_right_drag)
    coronal_label.bind('<B3-Motion>', tk_on_right_drag)
    sagittal_label.bind('<B3-Motion>', tk_on_right_drag)

    root.mainloop()


def run_gui(initial_folder: Optional[str] = None):
    # Choose backend: try PySimpleGUI first, then tkinter. If neither available, fallback to CLI mode.
    if sg is not None and hasattr(sg, 'Text') and hasattr(sg, 'Window') and hasattr(sg, 'Image'):
        return run_gui_sg(initial_folder)
    try:
        import tkinter  # type: ignore
        return run_gui_tkinter(initial_folder)
    except Exception:
        print('No GUI libraries available; running in CLI fallback mode')
        return run_cli(initial_folder)


def run_cli(folder: Optional[str] = None):
    # Minimal CLI fallback: load folder, show basic info, optionally save a slice
    if folder is None:
        print('Usage: python image.py <DICOM_FOLDER>')
        return
    if not os.path.isdir(folder):
        print('Folder not found:', folder)
        return
    try:
        volume, meta = load_dicom_series(folder)
    except Exception as e:
        print('Failed to load DICOM series:', e)
        return
    print('Loaded volume shape (Z,H,W):', volume.shape)
    print('Patient:', meta.get('patient_name', 'Unknown'))
    print('Patient ID:', meta.get('patient_id', 'Unknown'))
    # save middle axial slice by default
    z = volume.shape[0] // 2
    center = meta.get('window_center', 0)
    width = meta.get('window_width', 1)
    img8 = apply_window_level(volume[z], center, width)
    out = normalize_display_image(img8, (volume.shape[1], volume.shape[2]), 'Axial')
    outname = os.path.join(folder, 'slice_mid.png')
    Image.fromarray(out).save(outname)
    print('Saved middle axial slice to', outname)


def main():
    initial = None
    if len(sys.argv) > 1:
        initial = sys.argv[1]
    run_gui(initial)


if __name__ == '__main__':
    main()
