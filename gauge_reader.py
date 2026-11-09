#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
7セグ表示器の画像認識モジュール。

MainWindowからの使用例
----------------------
reader = GaugeReader(
    cam_id=1,
    model_path="7seg_svm_model.joblib",
)

reader.select_rois()   # 左の桁から順に4桁分のROIを設定
value = reader.read_value()
reader.close()
"""

from collections import Counter, deque
from pathlib import Path
import time

import cv2
import joblib
import numpy as np


def find_camera_id(max_devices=10):
    for camera_id in range(max_devices):
        cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                continue

            ok, frame = cap.read()
            if ok and frame is not None:
                return camera_id
        finally:
            cap.release()

# dont want to termiante.
    # raise RuntimeError("使用可能なカメラが見つかりません。")
    return None


N_DIGITS = 4
MODEL_PATH = "7seg_svm_model.joblib"

IMG_W = 32
IMG_H = 64
PAD_X = 4
PAD_Y = 4
SMOOTH_WINDOW = 5
CONF_THRESHOLD = 0.0


def make_hog():
    return cv2.HOGDescriptor(
        _winSize=(IMG_W, IMG_H),
        _blockSize=(16, 16),
        _blockStride=(8, 8),
        _cellSize=(8, 8),
        _nbins=9,
    )


HOG = make_hog()


def preprocess_image(img):
    """画像を黒背景・白い点灯セグメントへ変換する。"""

    if img is None:
        raise ValueError("画像がNoneです。")

    if img.size == 0:
        raise ValueError("画像サイズが0です。")

    if len(img.shape) == 3:
        b, g, r = cv2.split(img)
        gray = cv2.max(cv2.max(r, g), b)
    else:
        gray = img.copy()

    gray = cv2.resize(
        gray,
        (IMG_W, IMG_H),
        interpolation=cv2.INTER_AREA,
    )
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    _, bw = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    white_ratio = np.count_nonzero(bw) / bw.size
    if white_ratio > 0.5:
        bw = cv2.bitwise_not(bw)

    kernel = np.ones((2, 2), np.uint8)
    return cv2.morphologyEx(
        bw,
        cv2.MORPH_CLOSE,
        kernel,
    )


def extract_feature(img):
    proc = preprocess_image(img)

    hog_feat = HOG.compute(proc).flatten().astype(np.float32)
    pix_feat = proc.astype(np.float32).flatten() / 255.0

    return np.concatenate([hog_feat, pix_feat])


def predict_digits(model, crops):
    """桁ごとに切り出した画像のリストを認識する。"""

    features = []
    preprocessed = []

    for crop in crops:
        if crop is None or crop.size == 0:
            raise ValueError("桁画像の切り出しに失敗しました。")

        proc = preprocess_image(crop)
        preprocessed.append(proc)
        features.append(extract_feature(crop))

    x_data = np.array(features, dtype=np.float32)
    labels = model.predict(x_data)

    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(x_data)
        confidences = np.max(probabilities, axis=1)
    else:
        confidences = np.ones(
            len(labels),
            dtype=np.float32,
        )

    labels = [str(value) for value in labels]
    confidences = [float(value) for value in confidences]

    return labels, confidences, preprocessed


def majority_vote(history):
    if not history:
        return ""

    return Counter(history).most_common(1)[0][0]


class GaugeReader:
    """カメラ、ROI、SVMモデルを保持するゲージ読取りクラス。"""

    def __init__(
        self,
        cam_id,
        model_path=MODEL_PATH,
        n_digits=N_DIGITS,
        smooth_window=SMOOTH_WINDOW,
        confidence_threshold=CONF_THRESHOLD,
    ):
        self.cam_id = cam_id
        self.n_digits = n_digits
        self.smooth_window = smooth_window
        self.confidence_threshold = confidence_threshold

        path = Path(model_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent / path

        self.model_path = path
        self.model = None
        self.class_names = None
        self.cap = None
        # 桁ごとのROI。左の桁から順に (x, y, width, height)。
        self.rois = [None] * self.n_digits
        self.last_value = None
        self.preview_history = deque(maxlen=self.smooth_window)

    @property
    def has_roi(self):
        """全桁のROIが設定済みならTrue。"""
        return all(roi is not None for roi in self.rois)

    @property
    def is_camera_open(self):
        return (
            self.cap is not None
            and self.cap.isOpened()
        )

    def load_model(self):
        """SVMモデルを必要時に1回だけ読み込む。"""

        if self.model is not None:
            return

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"SVMモデルが見つかりません: {self.model_path}"
            )

        bundle = joblib.load(self.model_path)

        if isinstance(bundle, dict) and "model" in bundle:
            self.model = bundle["model"]
            self.class_names = bundle.get("class_names")
        else:
            self.model = bundle
            self.class_names = None

    def open_camera(self):
        """カメラを必要時に1回だけ開く。"""

        if self.is_camera_open:
            return True

        if self.cam_id is None:
            return False

        self.cap = cv2.VideoCapture(
            self.cam_id,
            cv2.CAP_DSHOW,
        )

        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            print(f"カメラを開けませんでした: CAM_ID={self.cam_id}")
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        self.cap.set(cv2.CAP_PROP_EXPOSURE, -1)
        self.cap.set(cv2.CAP_PROP_GAIN, 0)
        self.cap.set(cv2.CAP_PROP_BRIGHTNESS, 80)

        # カメラを開いた直後の不安定なフレームを捨てる。
        for _ in range(5):
            self.cap.read()

        return True

    def select_rois(self):
        """
        カメラ画像を表示し、左の桁から順に1桁ずつROIを設定する。

        各桁で、マウスドラッグ → Enter/Spaceで確定、
        cまたはEscでキャンセル（全体を中止し、既存ROIは維持）。
        戻り値は [(x, y, w, h), ...]。
        """

        self.load_model()
        self.open_camera()

        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise RuntimeError("ROI設定用フレームの取得に失敗しました。")

        window_name = "Select Digit ROI"
        new_rois = []

        try:
            for index in range(self.n_digits):
                guide = frame.copy()

                # 設定済みの桁を描画して、位置関係を分かりやすくする
                for done_index, done in enumerate(new_rois):
                    dx, dy, dw, dh = done
                    cv2.rectangle(
                        guide,
                        (dx, dy),
                        (dx + dw, dy + dh),
                        (0, 255, 0),
                        2,
                    )
                    cv2.putText(
                        guide,
                        str(done_index + 1),
                        (dx, max(dy - 6, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                        cv2.LINE_AA,
                    )

                cv2.putText(
                    guide,
                    f"Digit {index + 1}/{self.n_digits} (from left)",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

                selected = cv2.selectROI(
                    window_name,
                    guide,
                    showCrosshair=True,
                    fromCenter=False,
                )

                x, y, width, height = (
                    int(value) for value in selected
                )

                if width <= 0 or height <= 0:
                    raise RuntimeError(
                        f"{index + 1}桁目のROI設定がキャンセルされました。"
                    )

                new_rois.append((x, y, width, height))
        finally:
            cv2.destroyWindow(window_name)

        self.rois = new_rois
        self.last_value = None
        self.preview_history.clear()

        return list(self.rois)

    def set_rois(self, rois):
        """保存済みROIなどを外部から設定する。"""

        if rois is None or len(rois) != self.n_digits:
            raise ValueError(
                f"ROIは{self.n_digits}個の(x, y, width, height)で指定してください。"
            )

        checked = []
        for roi in rois:
            if roi is None or len(roi) != 4:
                raise ValueError(
                    "各ROIは(x, y, width, height)で指定してください。"
                )

            x, y, width, height = (int(value) for value in roi)

            if width <= 0 or height <= 0:
                raise ValueError("ROIの幅と高さは正の値が必要です。")

            checked.append((x, y, width, height))

        self.rois = checked
        self.last_value = None
        self.preview_history.clear()

    def _read_frame(self):
        self.open_camera()

        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise RuntimeError("カメラフレームの取得に失敗しました。")

        return frame

    def _crop_digit_rois(self, frame):
        """桁ごとのROIでフレームを切り出し、画像のリストを返す。"""

        if not self.has_roi:
            raise RuntimeError("ROIが未設定です。先にROI設定を実行してください。")

        frame_height, frame_width = frame.shape[:2]
        crops = []

        for index, (x, y, width, height) in enumerate(self.rois):
            if (
                x < 0
                or y < 0
                or x + width > frame_width
                or y + height > frame_height
            ):
                raise RuntimeError(
                    f"{index + 1}桁目のROIが現在のカメラ画像範囲から外れています。"
                )

            crop = frame[
                y:y + height,
                x:x + width,
            ]

            if crop.size == 0:
                raise RuntimeError(
                    f"{index + 1}桁目のROI画像の切り出しに失敗しました。"
                )

            crops.append(crop)

        return crops

    def analyze_frame(self, frame):
        """
        すでに取得済みのフレームを認識する（カメラからは読まない）。

        GUIのタイマーが読んだフレームを使い回すためのメソッド。
        戻り値は (labels, confidences, stable_text)。
        labelsは信頼度が閾値未満の桁を "?" にした文字のリスト。
        stable_textは直近smooth_window回の多数決結果。
        """

        self.load_model()
        crops = self._crop_digit_rois(frame)

        labels, confidences, _ = predict_digits(
            self.model,
            crops,
        )

        shown = [
            label if confidence >= self.confidence_threshold else "?"
            for label, confidence in zip(labels, confidences)
        ]

        self.preview_history.append("".join(shown))
        stable_text = majority_vote(self.preview_history)

        return shown, confidences, stable_text

    def read_once(self):
        """1フレームを認識し、認識文字列を返す。"""

        self.load_model()
        frame = self._read_frame()
        crops = self._crop_digit_rois(frame)

        labels, confidences, _ = predict_digits(
            self.model,
            crops,
        )

        text_chars = []
        for label, confidence in zip(labels, confidences):
            if confidence >= self.confidence_threshold:
                text_chars.append(label)
            else:
                text_chars.append("?")

        return "".join(text_chars)

    def get_live_frame(self):
        """
        ライブ表示用の1フレームを取得する。

        ROI設定済みなら、桁枠・認識結果を描画する。
        戻り値は (BGR画像, 安定化した認識文字列)。
        ROI未設定時の認識文字列は空文字列。
        """

        self.load_model()
        frame = self._read_frame()
        display = frame.copy()

        if not self.has_roi:
            cv2.putText(
                display,
                "ROI NOT SET",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 0, 255),
                3,
                cv2.LINE_AA,
            )
            return display, ""

        crops = self._crop_digit_rois(frame)
        labels, confidences, _ = predict_digits(
            self.model,
            crops,
        )

        raw_chars = []
        for label, confidence in zip(labels, confidences):
            if confidence >= self.confidence_threshold:
                raw_chars.append(label)
            else:
                raw_chars.append("?")

        raw_text = "".join(raw_chars)
        self.preview_history.append(raw_text)
        stable_text = majority_vote(self.preview_history)

        for roi, label, confidence in zip(
            self.rois,
            labels,
            confidences,
        ):
            x, y, width, height = roi
            gx1 = x
            gy1 = y
            gx2 = x + width
            gy2 = y + height

            if confidence >= self.confidence_threshold:
                shown_label = label
                color = (0, 255, 0)
            else:
                shown_label = "?"
                color = (0, 0, 255)

            cv2.rectangle(
                display,
                (gx1, gy1),
                (gx2, gy2),
                color,
                2,
            )
            cv2.putText(
                display,
                f"{shown_label} {confidence:.2f}",
                (gx1, max(gy1 - 6, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

        cv2.putText(
            display,
            f"READ: {stable_text}",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 255, 0),
            3,
            cv2.LINE_AA,
        )

        return display, stable_text

    def read_value(
        self,
        sample_count=None,
        frame_interval_sec=0.03,
    ):
        """
        複数フレームを認識し、多数決した数値文字列を返す。

        戻り値は先頭ゼロを保持するため文字列とする。
        """

        if sample_count is None:
            sample_count = self.smooth_window

        if sample_count <= 0:
            raise ValueError("sample_countは1以上が必要です。")

        history = deque(maxlen=sample_count)

        for index in range(sample_count):
            history.append(self.read_once())

            if (
                frame_interval_sec > 0
                and index < sample_count - 1
            ):
                time.sleep(frame_interval_sec)

        stable_text = majority_vote(history)
        stable_text = str(stable_text).strip()

        if not stable_text:
            raise RuntimeError("画像認識結果が空です。")

        if "?" in stable_text:
            raise RuntimeError(
                f"画像認識に失敗した桁があります: {stable_text}"
            )

        try:
            float(stable_text)
        except ValueError as error:
            raise RuntimeError(
                f"画像認識結果が数値ではありません: {stable_text}"
            ) from error

        self.last_value = stable_text
        return stable_text

    def close(self):
        """カメラとOpenCVウィンドウを閉じる。"""

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        cv2.destroyAllWindows()


def main():
    """このファイル単独でROI設定と1回読取りを試す。"""

    reader = GaugeReader(cam_id=find_camera_id())

    try:
        rois = reader.select_rois()
        print("ROIs:", rois)

        while True:
            value = reader.read_value()
            print("READ:", value)

            command = input(
                "Enterで再読取り、rでROI再設定、qで終了: "
            ).strip().lower()

            if command == "q":
                break

            if command == "r":
                print("ROIs:", reader.select_rois())

    finally:
        reader.close()


if __name__ == "__main__":
    main()