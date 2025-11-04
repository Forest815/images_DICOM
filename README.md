# image.py — Simple DICOM series viewer

このリポジトリに含まれる `image.py` は、教育目的の軽量な DICOM（CT/MR）シリーズビューアです。
以下は実行方法、依存関係、仕様（重要: GUI バックエンドによる挙動差）とトラブルシューティングのまとめです。

## 主な機能

- DICOM フォルダを読み込み、スライスを Z 軸方向にスタックして 3D ボリュームを作成
- Axial / Coronal / Sagittal 表示とスライダでのスライス移動
- Window/Level（center, width）調整（スライダ）
- 表示中スライスの PNG 保存
- PySimpleGUI を優先して使用、問題があれば tkinter にフォールバック

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

カレントフォルダに移動して:

```bash
python image.py
```

または DICOM フォルダを明示的に指定:

```bash
python image.py "C:\path\to\dicom_folder"
```

引数なしで起動すると、`DEFAULT_DICOM_FOLDER` に設定されたフォルダが自動的に読み込まれます（必要に応じて `image.py` 内の定数を書き換えて下さい）。

## GUI の挙動（重要）

`image.py` は実行時に利用可能な GUI バックエンドを次の順序で選択します:

1. PySimpleGUI が利用可能 -> `run_gui_sg` を使用
2. tkinter を使用できれば -> `run_gui_tkinter` を使用
3. どちらも使えない環境 -> CLI フォールバック（中間スライスを `slice_mid.png` として保存）

注意: PySimpleGUI と tkinter でスライダのラベルと内部で渡される意味が異なる実装になっているため、環境によって操作感や保存結果が変わることがあります。以下を必ずご確認ください。

### PySimpleGUI の挙動（推奨）

- UI 上のラベル:
	- 上スライダ: "Window Width"（キー: `-UI_WWIDTH-`）
	- 下スライダ: "Window Level"（キー: `-UI_WLEVEL-`）
- ライブ表示（レンダリング）と保存処理で使われる WL のマッピングは、現在の実装では同一になるよう修正済みです（center = `-UI_WLEVEL-`, width = `-UI_WWIDTH-`）。

### tkinter の挙動（フォールバック）

- UI 上のラベルは同じですが、現行実装では内部変数 `ui_window_width_var`（上） / `ui_window_level_var`（下）がそれぞれ center / width として扱われています。
- つまり tkinter 使用時は「上スライダ = center、下スライダ = width」となります。表示と保存はこのマッピングに従います。

（推奨）混乱を避けるため、両バックエンドとも UI ラベルに合わせた挙動（上=Width, 下=Center）に統一することをおすすめします。マニュアルとコードに修正手順を記載しています。

## 重要: Window/Level の取扱い

- コア関数: `apply_window_level(slice_img, center, width)` — 第1引数が center（ウィンドウ中心）、第2引数が width（ウィンドウ幅）です。
- 表示・保存で同じ WL を使うには、GUI 側で center と width を同じ順序で読み取り、`apply_window_level` に渡す必要があります。

## 保存（Save Slice）

- PySimpleGUI 使用時は GUI の Save ボタンから保存ダイアログが現れます。保存画像は現在の表示に対応する WL（上=幅、下=中心 のマッピング）で作成されるように修正済みです。
- tkinter 使用時は Save Axial ボタンでファイル選択ダイアログが出ます。tkinter の現行実装では上スライダを center、下スライダを width として保存されます。必要ならこちらも修正可能です。

## よくあるトラブルと対応

- PySimpleGUI が原因で GUI が立ち上がらない
	- Windows では非公式パッケージが混在していると不具合が出ることがあります。`pip uninstall PySimpleGUI` してから再インストールする、または tkinter を使用してください。
- DICOM フォルダが読み込めない
	- フォルダ内に PixelData を持つ DICOM ファイル (.dcm 等) があるか確認してください。
- 表示と保存で画面が異なる
	- これは center/width の読み取り順が異なることが原因です。`image.py` の `run_gui_sg` / `run_gui_tkinter` 内の apply_window_level 呼び出しとスライダの割当を確認／統一してください。

## 開発者向け: どこを直せば良いか（修正例）

- PySimpleGUI 側を UI 表示どおりに統一する場合（上=Width, 下=Center）:
	- `render_panes` 内で
		```py
		center = float(window['-UI_WLEVEL-'].get())
		width = float(window['-UI_WWIDTH-'].get())
		```
		としていることを確認し、
	- Save 処理でも同じ順序で apply_window_level(slice, center, width) を呼ぶようにします。

- tkinter 側を UI 表示どおりに直す場合:
	- `update_display` / `on_save` で現在 `wc = ui_window_width_var.get()` / `ww = ui_window_level_var.get()` となっている箇所を、
		```py
		center = ui_window_level_var.get()
		width = ui_window_width_var.get()
		```
		のように入れ替えてから `apply_window_level(center, width)` を呼ぶようにします。

## ライセンス・貢献

- 教育目的のサンプルコードです。必要に応じて改善・PR を歓迎します。

## 参考: 実行例

```bash
python image.py "C:\path\to\dicom_folder"
```

起動後、Open Folder からフォルダを指定して表示を確認してください。

---
更新: README は `image.py` の現行実装（2025年10月時点）に合わせて作成しています。GUI の統一やさらなる改善が必要なら、私の方で `image.py` の修正とテスト（静的チェック）を引き続き行えます。ご希望を教えてください。
