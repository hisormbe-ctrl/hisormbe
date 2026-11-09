#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Jun 2026.10.29
#

from PySide6.QtCore import Signal, Qt, QTimer, QPoint
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PySide6.QtGui import QImage, QPixmap

import cv2
from gauge_reader import GaugeReader


class ImageLabel(QLabel):
    """マウス操作を通知するライブ画像表示用ラベル。"""

    pressed = Signal(QPoint)
    moved = Signal(QPoint)
    released = Signal(QPoint)
    right_clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit(event.position().toPoint())
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.moved.emit(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.released.emit(event.position().toPoint())
        super().mouseReleaseEvent(event)


class Camera(QWidget):

    # これより小さいドラッグはROIとして扱わない（フレーム座標[px]）
    MIN_ROI_SIZE = 4

    # 認識は毎フレームではなくNフレームに1回行う（33ms × 3 ≒ 100ms）
    RECOGNIZE_EVERY_N_FRAMES = 3

    # 安定化した認識値が変わったときに通知する（例："0123"）
    value_changed = Signal(str)

    def __init__(self, camera_id):
        super().__init__()

        self.camera_id = camera_id
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # ----- 状態 -----
        self.frame = None            # 最新の元画像（BGR）
        self._view = None            # (offset_x, offset_y, scale) 画面→フレーム変換用
        self.roi_editing = False     # ROI設定中か
        self.new_rois = []           # 設定中の確定済みROI
        self.drag_start = None       # ドラッグ開始点（フレーム座標）
        self.drag_end = None         # ドラッグ現在点（フレーム座標）

        self.recognizing = False     # 認識中か
        self._frame_count = 0
        self.last_labels = []        # 直近の桁ごとの認識結果
        self.last_confidences = []
        self.read_text = ""          # 安定化した認識値

        # ----- 部品 -----
        self.status_label = QLabel()

        self.camera_settings_button = QPushButton("設定")
        self.camera_settings_button.clicked.connect(
            self.open_camera_settings
        )

        self.rois_settings_button = QPushButton("設定")
        self.rois_settings_button.clicked.connect(
            self.toggle_roi_editing
        )

        self.recognize_button = QPushButton("開始")
        self.recognize_button.clicked.connect(
            self.toggle_recognition
        )

        self.value_label = QLabel("READ: ----")
        self.value_label.setObjectName("gaugeValue")

        self.picture_label = QLabel("カメラ画像")

        # ライブ画像（ROIもここに重ねて描画・設定する）
        self.image_label = ImageLabel()
        self.image_label.setMinimumSize(640, 480)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.pressed.connect(self.on_image_pressed)
        self.image_label.moved.connect(self.on_image_moved)
        self.image_label.released.connect(self.on_image_released)
        self.image_label.right_clicked.connect(self.undo_last_roi)

        layout = QVBoxLayout(self)
        camera_label = QLabel("カメラ")
        camera_label.setObjectName("sectionLabel")

        roi_label = QLabel("ROI")
        roi_label.setObjectName("sectionLabel")

        roi_buttons = QHBoxLayout()
        roi_buttons.addWidget(self.rois_settings_button, 1)
        roi_buttons.addWidget(self.recognize_button, 1)

        layout.addWidget(self.status_label)
        layout.addWidget(camera_label)
        layout.addWidget(self.camera_settings_button)
        layout.addWidget(roi_label)
        layout.addLayout(roi_buttons)
        layout.addWidget(self.value_label)
        layout.addWidget(self.picture_label)
        layout.addWidget(self.image_label)

        # ----- カメラ -----
        self.gauge_reader = GaugeReader(cam_id=camera_id)
        self.gauge_reader.open_camera()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(33)

        layout.addStretch()
        self.update_camera_status()

    # ------------------------------------------------------------
    # 状態表示
    # ------------------------------------------------------------

    def update_camera_status(self):
        if self.gauge_reader.is_camera_open:
            self.status_label.setText(
                f"Camera ID {self.camera_id}：接続成功"
            )
            self.camera_settings_button.setEnabled(True)
            self.rois_settings_button.setEnabled(True)
            self.recognize_button.setEnabled(True)
        else:
            self.status_label.setText(
                f"Camera ID {self.camera_id}：接続失敗"
            )
            self.camera_settings_button.setEnabled(False)
            self.rois_settings_button.setEnabled(False)
            self.recognize_button.setEnabled(False)

    def _show_roi_guide(self):
        n_digits = self.gauge_reader.n_digits
        index = len(self.new_rois) + 1
        self.status_label.setText(
            f"ROI設定：{index}/{n_digits}桁目（左から）を"
            "ドラッグで囲んでください。"
            "右クリックで1つ戻る / Escまたはボタンで中止"
        )

    # ------------------------------------------------------------
    # ROI設定
    # ------------------------------------------------------------

    def toggle_roi_editing(self):
        if self.roi_editing:
            self.cancel_roi_editing()
        else:
            self.start_roi_editing()

    def start_roi_editing(self):
        if not self.gauge_reader.is_camera_open:
            self.status_label.setText("ROI設定：カメラが接続されていません。")
            return

        self.roi_editing = True
        self.new_rois = []
        self.drag_start = None
        self.drag_end = None

        self.rois_settings_button.setText("中止")
        self.image_label.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocus()
        self._show_roi_guide()

    def cancel_roi_editing(self, message="ROI設定を中止しました（既存ROIは維持）。"):
        self._end_roi_editing()
        self.status_label.setText(message)

    def _end_roi_editing(self):
        self.roi_editing = False
        self.new_rois = []
        self.drag_start = None
        self.drag_end = None

        self.rois_settings_button.setText("設定")
        self.image_label.unsetCursor()

    def undo_last_roi(self):
        """設定中、右クリックで直前の桁を取り消す。"""

        if not self.roi_editing:
            return

        self.drag_start = None
        self.drag_end = None

        if self.new_rois:
            self.new_rois.pop()

        self._show_roi_guide()

    def _finish_roi_editing(self):
        rois = list(self.new_rois)

        try:
            self.gauge_reader.set_rois(rois)
        except Exception as error:
            self._end_roi_editing()
            self.status_label.setText(f"ROI設定に失敗：{error}")
            return

        self._end_roi_editing()
        self.status_label.setText(
            f"ROI設定完了：{len(rois)}桁"
        )

    def keyPressEvent(self, event):
        if (
            event.key() == Qt.Key.Key_Escape
            and self.roi_editing
        ):
            self.cancel_roi_editing()
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------
    # マウス操作（画面座標 → フレーム座標）
    # ------------------------------------------------------------

    def _label_to_frame(self, pos):
        """ラベル上の座標を元画像の座標へ変換する。変換不可ならNone。"""

        if self._view is None or self.frame is None:
            return None

        offset_x, offset_y, scale = self._view
        if scale <= 0:
            return None

        frame_height, frame_width = self.frame.shape[:2]

        x = int(round((pos.x() - offset_x) / scale))
        y = int(round((pos.y() - offset_y) / scale))

        x = min(max(x, 0), frame_width - 1)
        y = min(max(y, 0), frame_height - 1)

        return x, y

    def on_image_pressed(self, pos):
        if not self.roi_editing:
            return

        point = self._label_to_frame(pos)
        if point is None:
            return

        self.drag_start = point
        self.drag_end = point

    def on_image_moved(self, pos):
        if not self.roi_editing or self.drag_start is None:
            return

        point = self._label_to_frame(pos)
        if point is not None:
            self.drag_end = point

    def on_image_released(self, pos):
        if not self.roi_editing or self.drag_start is None:
            return

        point = self._label_to_frame(pos)
        if point is not None:
            self.drag_end = point

        x1, y1 = self.drag_start
        x2, y2 = self.drag_end

        self.drag_start = None
        self.drag_end = None

        x = min(x1, x2)
        y = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        # 小さすぎるドラッグ（クリックのみ等）は無視
        if width < self.MIN_ROI_SIZE or height < self.MIN_ROI_SIZE:
            return

        self.new_rois.append((x, y, width, height))

        if len(self.new_rois) >= self.gauge_reader.n_digits:
            self._finish_roi_editing()
        else:
            self._show_roi_guide()

    # ------------------------------------------------------------
    # 認識
    # ------------------------------------------------------------

    def toggle_recognition(self):
        if self.recognizing:
            self.stop_recognition()
        else:
            self.start_recognition()

    def start_recognition(self):
        if self.roi_editing:
            self.status_label.setText(
                "認識：ROI設定を完了または中止してから開始してください。"
            )
            return

        if not self.gauge_reader.has_roi:
            self.status_label.setText(
                "認識：先にROI設定で全桁のROIを設定してください。"
            )
            return

        try:
            # モデルを先に読み込み、失敗をここで知らせる
            self.gauge_reader.load_model()
        except Exception as error:
            self.status_label.setText(f"認識：{error}")
            return

        self.gauge_reader.preview_history.clear()
        self.read_text = ""
        self.last_labels = []
        self.last_confidences = []
        self._frame_count = 0

        self.recognizing = True
        self.recognize_button.setText("停止")
        self.status_label.setText("認識中")

    def stop_recognition(self, message="認識を停止しました。"):
        self.recognizing = False
        self.last_labels = []
        self.last_confidences = []
        self.recognize_button.setText("開始")
        self.value_label.setText("READ: ----")
        self.status_label.setText(message)

    def _recognize(self, frame):
        """Nフレームに1回、現在のフレームを認識して結果を保持する。"""

        self._frame_count += 1
        if self._frame_count % self.RECOGNIZE_EVERY_N_FRAMES != 0:
            return

        try:
            labels, confidences, text = self.gauge_reader.analyze_frame(
                frame
            )
        except Exception as error:
            self.stop_recognition(f"認識を停止：{error}")
            return

        self.last_labels = labels
        self.last_confidences = confidences

        self.value_label.setText(f"READ: {text}")

        if text != self.read_text:
            self.read_text = text
            self.value_changed.emit(text)

    # ------------------------------------------------------------
    # カメラ設定
    # ------------------------------------------------------------

    def open_camera_settings(self):

        cap = self.gauge_reader.cap
        if cap is None or not cap.isOpened():
            self.status_label.setText(
                "Camera not opened."
            )
            return

        # DirectShowのカメラ設定画面を開く
        cap.set(
            cv2.CAP_PROP_SETTINGS,
            1,
        )

    # ------------------------------------------------------------
    # ライブ画像
    # ------------------------------------------------------------

    def _draw_rois(self, display):
        """ROI枠と設定中のドラッグ枠を画像へ描画する。"""

        if self.roi_editing:
            rois = self.new_rois
        else:
            rois = [
                roi for roi in self.gauge_reader.rois
                if roi is not None
            ]

        show_result = (
            self.recognizing
            and not self.roi_editing
            and len(self.last_labels) == len(rois)
        )

        for index, (x, y, width, height) in enumerate(rois):
            color = (0, 255, 0)
            caption = str(index + 1)

            if show_result:
                label = self.last_labels[index]
                confidence = self.last_confidences[index]
                caption = f"{label} {confidence:.2f}"

                if label == "?":
                    color = (0, 0, 255)

            cv2.rectangle(
                display,
                (x, y),
                (x + width, y + height),
                color,
                2,
            )
            cv2.putText(
                display,
                caption,
                (x, max(y - 6, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
                cv2.LINE_AA,
            )

        if self.roi_editing:
            if self.drag_start is not None and self.drag_end is not None:
                cv2.rectangle(
                    display,
                    self.drag_start,
                    self.drag_end,
                    (0, 255, 255),
                    2,
                )

            cv2.putText(
                display,
                f"Digit {len(self.new_rois) + 1}/{self.gauge_reader.n_digits}",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

    def update_frame(self):

        cap = self.gauge_reader.cap
        if cap is None or not cap.isOpened():
            self.image_label.setText("カメラが接続されていません")
            return

        ret, frame = cap.read()

        if not ret:
            self.image_label.setText("画像を取得できませんでした")
            return

        # 元画像を保持（ROI座標・画像認識用。描画は入れない）
        self.frame = frame

        # 認識（ROI設定中は行わない）
        if self.recognizing and not self.roi_editing:
            self._recognize(frame)

        # 表示用コピーにROI枠を描画
        display = frame.copy()
        self._draw_rois(display)

        # OpenCVのBGR画像をRGBに変換
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)

        height, width, _ = rgb.shape

        image = QImage(
            rgb.data,
            width,
            height,
            rgb.strides[0],
            QImage.Format.Format_RGB888,
        ).copy()

        pixmap = QPixmap.fromImage(image)

        pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # マウス座標→フレーム座標の変換情報（中央寄せ表示を考慮）
        self._view = (
            (self.image_label.width() - pixmap.width()) / 2,
            (self.image_label.height() - pixmap.height()) / 2,
            pixmap.width() / width,
        )

        self.image_label.setPixmap(pixmap)


if __name__=='__main__':

    print("Camera...")