import os
import json
import cv2
import joblib
import numpy as np

from sklearn.svm import SVC
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score


# ===== 設定 =====
IMG_W = 32
IMG_H = 64

MODEL_PATH = "7seg_svm_model.joblib"

CANDIDATE_DATA_DIRS = [
    "dataset_aug/digits",
    "dataset_aug",
    "dataset/digits",
    "dataset",
]

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp")


def find_data_dir():
    for d in CANDIDATE_DATA_DIRS:
        if os.path.isdir(d):
            class_dirs = [
                name for name in os.listdir(d)
                if os.path.isdir(os.path.join(d, name))
            ]
            if len(class_dirs) > 0:
                return d

    raise FileNotFoundError(
        "教師データフォルダが見つかりません。"
        " dataset_aug/0〜9 または dataset_aug/digits/0〜9 を確認してください。"
    )


def make_hog():
    """
    32x64画像用HOG特徴量。
    """
    hog = cv2.HOGDescriptor(
        _winSize=(IMG_W, IMG_H),
        _blockSize=(16, 16),
        _blockStride=(8, 8),
        _cellSize=(8, 8),
        _nbins=9,
    )
    return hog


HOG = make_hog()


def preprocess_image(img):
    """
    7セグ用前処理。
    色付きLEDでも教師画像でも、最終的に
    黒背景 + 白い点灯セグメント
    にそろえる。
    """
    if img is None:
        raise ValueError("画像がNoneです。")

    if len(img.shape) == 3:
        # BGR
        b, g, r = cv2.split(img)

        # 赤LED・緑LED・白LEDのどれでも拾いやすいように最大チャンネルを使う
        gray = cv2.max(cv2.max(r, g), b)
    else:
        gray = img.copy()

    # サイズ統一
    gray = cv2.resize(gray, (IMG_W, IMG_H), interpolation=cv2.INTER_AREA)

    # ノイズを少し丸める
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # 重要：equalizeHist は使わない
    # Otsuで点灯部だけ抽出
    _, bw = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # 背景の白飛びなどで反転してしまった場合の保険
    # 点灯セグメントは画像全体の半分未満のはず
    white_ratio = np.count_nonzero(bw) / bw.size
    if white_ratio > 0.5:
        bw = cv2.bitwise_not(bw)

    # 小さい穴やギザギザを少し補正
    kernel = np.ones((2, 2), np.uint8)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)

    return bw

def extract_feature(img):
    """
    HOG特徴量 + 画素値特徴量を結合する。
    HOGだけより7セグでは安定することがあります。
    """
    proc = preprocess_image(img)

    hog_feat = HOG.compute(proc).flatten().astype(np.float32)

    pix_feat = proc.astype(np.float32).flatten() / 255.0

    feat = np.concatenate([hog_feat, pix_feat])

    return feat


def load_dataset(data_dir):
    X = []
    y = []
    paths = []

    class_names = [
        name for name in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, name))
    ]

    # 0,1,2,...,9 の順にしたいので文字列ソート
    class_names = sorted(class_names)

    print("data_dir =", data_dir)
    print("class_names =", class_names)

    for label in class_names:
        label_dir = os.path.join(data_dir, label)

        files = [
            f for f in os.listdir(label_dir)
            if f.lower().endswith(IMAGE_EXTS)
        ]

        print(f"{label}: {len(files)} images")

        for fname in files:
            path = os.path.join(label_dir, fname)

            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                print("WARNING: 読めない画像:", path)
                continue

            feat = extract_feature(img)

            X.append(feat)
            y.append(label)
            paths.append(path)

    if len(X) == 0:
        raise RuntimeError("教師画像が1枚も読み込めませんでした。")

    X = np.array(X, dtype=np.float32)
    y = np.array(y)

    return X, y, class_names, paths


def main():
    data_dir = find_data_dir()

    X, y, class_names, paths = load_dataset(data_dir)

    print("")
    print("Total images:", len(y))
    print("Feature dim:", X.shape[1])
    print("")

    # データが少ない場合でも一応動くようにする
    stratify = y if len(set(y)) > 1 else None

    X_train, X_val, y_train, y_val = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=123,
        stratify=stratify,
    )

    # SVM分類器
    model = make_pipeline(
        StandardScaler(),
        SVC(
            kernel="rbf",
            C=10.0,
            gamma="scale",
            probability=True,
            class_weight="balanced",
        )
    )

    print("Training SVM...")
    model.fit(X_train, y_train)

    print("Validation...")
    y_pred = model.predict(X_val)

    acc = accuracy_score(y_val, y_pred)
    print("")
    print("accuracy =", acc)
    print("")

    print("classification_report:")
    print(classification_report(y_val, y_pred, zero_division=0))

    print("confusion_matrix:")
    print(confusion_matrix(y_val, y_pred, labels=class_names))

    bundle = {
        "model": model,
        "class_names": class_names,
        "img_w": IMG_W,
        "img_h": IMG_H,
        "feature": "hog_plus_pixels",
    }

    joblib.dump(bundle, MODEL_PATH)

    print("")
    print("保存しました:", MODEL_PATH)


if __name__ == "__main__":
    main()