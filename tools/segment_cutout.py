from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def color_distance(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.max(np.abs(left.astype(np.int16) - right.astype(np.int16)), axis=-1)


def detect_checkerboard_colors(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    height, width, _ = image.shape
    samples = np.array(
        [
            image[0, 0],
            image[0, width - 1],
            image[height - 1, 0],
            image[height - 1, width - 1],
            image[0, width // 2],
            image[height - 1, width // 2],
            image[height // 2, 0],
            image[height // 2, width - 1],
        ],
        dtype=np.uint8,
    )

    clusters: list[np.ndarray] = []
    for color in samples:
        if not clusters:
            clusters.append(color)
            continue
        if any(np.max(np.abs(color.astype(np.int16) - seen.astype(np.int16))) <= 10 for seen in clusters):
            continue
        clusters.append(color)

    if len(clusters) != 2:
        return None

    first, second = clusters
    if np.max(np.abs(first.astype(np.int16) - second.astype(np.int16))) < 8:
        return None
    return first, second


def build_initial_mask(height: int, width: int) -> np.ndarray:
    mask = np.full((height, width), cv2.GC_PR_BGD, dtype=np.uint8)

    border_x = max(24, width // 12)
    border_y = max(24, height // 12)
    mask[:border_y, :] = cv2.GC_BGD
    mask[-border_y:, :] = cv2.GC_BGD
    mask[:, :border_x] = cv2.GC_BGD
    mask[:, -border_x:] = cv2.GC_BGD

    center_left = width // 5
    center_top = height // 12
    center_right = width - center_left
    center_bottom = height - max(24, height // 24)
    mask[center_top:center_bottom, center_left:center_right] = cv2.GC_PR_FGD

    inner_left = width // 3
    inner_top = height // 8
    inner_right = width - inner_left
    inner_bottom = height - max(16, height // 12)
    mask[inner_top:inner_bottom, inner_left:inner_right] = cv2.GC_FGD
    return mask


def apply_checkerboard_priors(
    image: np.ndarray,
    mask: np.ndarray,
    checkerboard: tuple[np.ndarray, np.ndarray] | None,
) -> np.ndarray:
    if checkerboard is None:
        return mask

    first, second = checkerboard
    distance = np.minimum(color_distance(image, first), color_distance(image, second))

    mask[distance <= 12] = cv2.GC_PR_BGD
    mask[distance >= 36] = cv2.GC_PR_FGD

    center_left = image.shape[1] // 4
    center_right = image.shape[1] - center_left
    center_top = image.shape[0] // 10
    center_bottom = image.shape[0] - max(24, image.shape[0] // 10)
    center_region = distance[center_top:center_bottom, center_left:center_right]
    mask_slice = mask[center_top:center_bottom, center_left:center_right]
    mask_slice[center_region >= 18] = cv2.GC_PR_FGD
    mask[center_top:center_bottom, center_left:center_right] = mask_slice
    return mask


def refine_alpha(mask: np.ndarray) -> np.ndarray:
    foreground = np.where(
        (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel, iterations=1)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
    foreground = cv2.GaussianBlur(foreground, (0, 0), sigmaX=1.2, sigmaY=1.2)
    return foreground


def recover_foreground_colors(
    image: np.ndarray,
    alpha: np.ndarray,
    checkerboard: tuple[np.ndarray, np.ndarray] | None,
) -> np.ndarray:
    rgba = np.dstack((image, alpha)).astype(np.float32)
    if checkerboard is None:
        return rgba.astype(np.uint8)

    first, second = checkerboard
    first = first.astype(np.float32)
    second = second.astype(np.float32)

    source = image.astype(np.float32)
    alpha_f = np.clip(alpha.astype(np.float32) / 255.0, 0.0, 1.0)

    distance_first = np.max(np.abs(source - first), axis=-1)
    distance_second = np.max(np.abs(source - second), axis=-1)
    background = np.where(
        (distance_first <= distance_second)[..., None],
        first,
        second,
    )

    # Use the segmentation alpha as the matte, then solve foreground RGB from
    # source = fg * alpha + bg * (1 - alpha).
    safe_alpha = np.clip(alpha_f, 1e-3, 1.0)[..., None]
    restored = (source - background * (1.0 - safe_alpha)) / safe_alpha
    restored = np.clip(restored, 0, 255)

    fully_transparent = alpha_f <= 0.01
    rgba[..., :3] = restored
    rgba[..., 3] = alpha.astype(np.float32)
    rgba[fully_transparent, :3] = 0
    return rgba.astype(np.uint8)


def strip_rectangular_checkerboard_residue(
    rgba: np.ndarray,
    checkerboard: tuple[np.ndarray, np.ndarray] | None,
) -> np.ndarray:
    if checkerboard is None:
        return rgba

    rgb = rgba[:, :, :3].astype(np.int16)
    alpha = rgba[:, :, 3]
    first = checkerboard[0].astype(np.int16)
    second = checkerboard[1].astype(np.int16)

    dist_first = np.max(np.abs(rgb - first), axis=-1)
    dist_second = np.max(np.abs(rgb - second), axis=-1)
    near_checker = np.minimum(dist_first, dist_second) <= 14
    strong_alpha = alpha >= 220

    residue = near_checker & strong_alpha
    if not np.any(residue):
        return rgba

    coords = np.argwhere(residue)
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)

    # Only clear large connected residue zones; keep small bright ornaments.
    width = x_max - x_min + 1
    height = y_max - y_min + 1
    if width < rgba.shape[1] // 6 or height < rgba.shape[0] // 6:
        return rgba

    candidate = residue.copy().astype(np.uint8) * 255
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    for label in range(1, num_labels):
        x, y, w, h, area = stats[label]
        touches_vertical_span = h >= rgba.shape[0] // 3
        near_center = abs((x + w / 2) - (rgba.shape[1] / 2)) <= rgba.shape[1] * 0.18
        large_enough = area >= (rgba.shape[0] * rgba.shape[1]) * 0.02
        if touches_vertical_span and near_center and large_enough:
            rgba[labels == label, 3] = 0
            rgba[labels == label, 0:3] = 0

    return rgba


def cutout(input_path: Path, output_path: Path) -> None:
    pil_image = Image.open(input_path).convert("RGB")
    image = np.array(pil_image)
    bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    checkerboard = detect_checkerboard_colors(image)

    mask = build_initial_mask(bgr.shape[0], bgr.shape[1])
    mask = apply_checkerboard_priors(image, mask, checkerboard)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    cv2.grabCut(
        bgr,
        mask,
        None,
        bgd_model,
        fgd_model,
        8,
        cv2.GC_INIT_WITH_MASK,
    )

    alpha = refine_alpha(mask)
    rgba = recover_foreground_colors(image, alpha, checkerboard)
    rgba = strip_rectangular_checkerboard_residue(rgba, checkerboard)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(output_path)


def clean_dragged_residue(input_path: Path, output_path: Path) -> None:
    image = np.array(Image.open(input_path).convert("RGBA"))
    rgb = image[:, :, :3].astype(np.int16)
    alpha = image[:, :, 3]

    # The dragged pose keeps a large checkerboard rectangle centered behind the
    # character. Remove bright low-saturation residue in that corridor while
    # preserving the hand and dark hair around the top knot.
    brightness = rgb.max(axis=-1)
    chroma = rgb.max(axis=-1) - rgb.min(axis=-1)

    h, w = alpha.shape
    corridor = np.zeros((h, w), dtype=bool)
    corridor[h // 8 : h - h // 10, w // 3 : w * 2 // 3] = True

    bright_neutral = (brightness >= 225) & (chroma <= 28) & (alpha >= 200) & corridor

    # Protect the top hand area and the central hair bun.
    bright_neutral[: h // 8, :] = False
    protect = np.zeros((h, w), dtype=bool)
    protect[h // 20 : h // 3, w // 2 - w // 10 : w // 2 + w // 10] = True
    bright_neutral[protect & (brightness < 250)] = False

    image[bright_neutral, 3] = 0
    image[bright_neutral, 0:3] = 0
    Image.fromarray(image, mode="RGBA").save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Segment a character image into RGBA.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--mode",
        choices=("default", "dragged-clean"),
        default="default",
    )
    args = parser.parse_args()

    if args.mode == "dragged-clean":
        clean_dragged_residue(args.input, args.output)
    else:
        cutout(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
