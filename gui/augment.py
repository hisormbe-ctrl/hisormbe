import cv2
import os
import random
import numpy as np


def augment_digit(img):
    h, w = img.shape[:2]

    # 明るさ・コントラスト
    alpha = random.uniform(0.8, 1.3)   # contrast
    beta = random.uniform(-20, 20)     # brightness
    out = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

    # ブラー
    if random.random() < 0.5:
        out = cv2.GaussianBlur(out, (3, 3), sigmaX=random.uniform(0.3, 1.2))

    # 小さい平行移動
    dx = random.uniform(-2, 2)
    dy = random.uniform(-2, 2)
    M = np.float32([
        [1, 0, dx],
        [0, 1, dy],
    ])
    out = cv2.warpAffine(
        out,
        M,
        (w, h),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    # ノイズ
    if random.random() < 0.5:
        noise = np.random.normal(0, 5, out.shape).astype(np.int16)
        out = np.clip(out.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    return out


def augment_folder(input_dir, output_dir, n_aug=20):
    os.makedirs(output_dir, exist_ok=True)

    for label in "0123456789":
        in_label_dir = os.path.join(input_dir, label)
        out_label_dir = os.path.join(output_dir, label)
        os.makedirs(out_label_dir, exist_ok=True)

        if not os.path.isdir(in_label_dir):
            continue

        files = [
            f for f in os.listdir(in_label_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ]

        for fname in files:
            path = os.path.join(in_label_dir, fname)
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

            if img is None:
                continue

            base, _ = os.path.splitext(fname)

            # 元画像も保存
            cv2.imwrite(os.path.join(out_label_dir, f"{base}_orig.png"), img)

            for i in range(n_aug):
                aug = augment_digit(img)
                out_name = f"{base}_aug{i:03d}.png"
                cv2.imwrite(os.path.join(out_label_dir, out_name), aug)


if __name__ == "__main__":
    augment_folder(
        input_dir="dataset/digits",
        output_dir="dataset_aug/digits",
        n_aug=30,
    )