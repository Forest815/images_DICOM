# image.py — Simple DICOM series viewer

このリポジトリに含まれる `image.py` は、教育目的の軽量な DICOM（CT/MR）シリーズビューアです。
以下は実行方法、依存関係、現行実装の挙動（重要: GUI バックエンドによる振る舞い差はほぼ解消済み）とトラブルシューティングのまとめです。

## 主な機能

- DICOM フォルダを読み込み、スライスを Z 軸方向にスタックして 3D ボリュームを作成
- Axial / Coronal / Sagittal 表示とスライダでのスライス移動
- Window/Level（center, width）調整（スライダ）
- 表示中スライスの PNG 保存
- PySimpleGUI を優先して使用し、利用不可のときは tkinter にフォールバック

## 要件

- Python 3.8 以降
- 必要なパッケージ（requirements.txt を使用）:
  - pydicom
  - numpy
  - pillow
  - （任意）PySimpleGUI

インストール例（Windows の cmd.exe）:

```bash
python -m pip install --user -r requirements.txt
```

## 実行方法

現在のフォルダで:

```bash
python image.py
```

または DICOM フォルダを明示的に指定:

```bash
python image.py "C:\path\to\dicom_folder"
```

引数なしで起動すると、`image.py` 内で指定された `DEFAULT_DICOM_FOLDER` が自動的に読み込まれます（必要に応じて書き換えてください）。

## GUI の挙動（重要）

`image.py` は起動時に利用可能な GUI バックエンドを次の順で選択します:

1. PySimpleGUI が利用可能 -> `run_gui_sg`
2. tkinter を使用できれば -> `run_gui_tkinter`
3. どちらも使えない環境 -> CLI フォールバック（中間スライスを `slice_mid.png` として保存）

注: 以前は PySimpleGUI と tkinter で WL スライダの内部マッピングに差異がありましたが、現在の実装では両方とも
「上スライダ = Window Width（幅）、下スライダ = Window Level（中心）」
のマッピングで動作するように統一されています。表示と保存で同じ WL が使われることを確認済みです。

### 共通 UI 情報

- 上（Window Width）スライダの範囲: 1 ～ 4000（初期値: 400）
- 下（Window Level = center）スライダの範囲: -2000 ～ 2000（初期値: 30）

（注）これらの初期値は、DICOM 内の WindowCenter / WindowWidth が存在する場合はその値を優先します。

## 保存（Save Slice）

- PySimpleGUI／tkinter のどちらでも、表示と同じ WL を使って保存されます。

## よくあるトラブルと対応

- PySimpleGUI が原因で GUI が立ち上がらない
  - Windows 環境で非公式パッケージが混在している場合があります。`pip uninstall PySimpleGUI` のあと再インストールするか、tkinter にフォールバックして試してください。
- DICOM フォルダが読み込めない
  - フォルダ内に PixelData を持つ DICOM ファイルがあるかを確認してください。

## CLI フォールバック

GUI が使えない環境では、指定フォルダを読み込み中間スライスを `slice_mid.png` として保存します。

## 参考: 実行例

```bash
python image.py "C:\path\to\dicom_folder"
```

起動後、Open Folder でフォルダを選ぶか、引数でフォルダを渡して動作確認してください。

---
更新: README は `image.py` の現行実装（更新: 2025年11月）に合わせて編集しました。追加の変更（例: WL の UI をさらに細かく制御するスクリプト化など）をご希望なら対応します。
