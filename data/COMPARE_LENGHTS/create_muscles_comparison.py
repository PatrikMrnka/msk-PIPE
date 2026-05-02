from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent
SOURCE_FOLDERS = [
    "LUCA_ATLAS_BASED",
    "LUCA_OWN_ATTACHMENTS",
    "LUCA_PROXIMITY_BASED_5mm",
]
OUTPUT_FOLDER = "LUCA"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
LABEL_FONT_SIZE = 108


def list_images(folder_path: Path) -> set[str]:
    return {
        file.name
        for file in folder_path.iterdir()
        if file.is_file() and file.suffix.lower() in ALLOWED_EXTENSIONS
        and "violin_group" not in file.name.lower()
    }


def load_label_font(size: int) -> ImageFont.ImageFont:
    # Try common fonts first; fall back to Pillow's default if unavailable.
    font_candidates = ["DejaVuSans.ttf", "arial.ttf"]
    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_comparison_image(image_paths: list[Path | None], labels: list[str], output_path: Path) -> None:
    loaded_images: list[tuple[Image.Image, str]] = []
    for path, label in zip(image_paths, labels):
        if path is None or not path.exists():
            continue
        with Image.open(path) as image:
            loaded_images.append((image.convert("RGB"), label))

    if not loaded_images:
        return

    target_height = max(image.height for image, _ in loaded_images)
    resized_images: list[tuple[Image.Image, str]] = []
    for image, label in loaded_images:
        if image.height == target_height:
            resized_images.append((image, label))
            continue
        new_width = int(image.width * (target_height / image.height))
        resized_images.append((image.resize((new_width, target_height), Image.Resampling.LANCZOS), label))

    font = load_label_font(LABEL_FONT_SIZE)
    draw_padding = 20
    gap = 20
    label_padding_y = 12

    measurement_draw = ImageDraw.Draw(Image.new("RGB", (1, 1), "white"))
    label_text_height = max(
        measurement_draw.textbbox((0, 0), label, font=font)[3]
        - measurement_draw.textbbox((0, 0), label, font=font)[1]
        for label in labels
    )
    label_height = label_text_height + 2 * label_padding_y

    panel_widths = [image.width for image, _ in resized_images]
    max_panel_width = max(panel_widths)
    row_height = label_height + target_height
    total_width = 2 * draw_padding + max_panel_width
    total_height = 2 * draw_padding + len(resized_images) * row_height + gap * (len(resized_images) - 1)

    canvas = Image.new("RGB", (total_width, total_height), "white")
    draw = ImageDraw.Draw(canvas)

    y = draw_padding

    for (image, label), panel_width in zip(resized_images, panel_widths):
        panel_x = draw_padding + (max_panel_width - panel_width) // 2
        y_image = y + label_height

        canvas.paste(image, (panel_x, y_image))

        text_bbox = draw.textbbox((0, 0), label, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_x = panel_x + (panel_width - text_width) // 2
        text_y = y + (label_height - (text_bbox[3] - text_bbox[1])) // 2
        draw.text((text_x, text_y), label, fill="black", font=font)

        y += row_height + gap

    canvas.save(output_path)



def main() -> None:
    source_paths = [BASE_DIR / folder for folder in SOURCE_FOLDERS]
    output_path = BASE_DIR / OUTPUT_FOLDER
    output_path.mkdir(parents=True, exist_ok=True)

    missing_dirs = [str(path) for path in source_paths if not path.exists()]
    if missing_dirs:
        raise FileNotFoundError(
            "Nebyly nalezeny slozky:\n" + "\n".join(missing_dirs)
        )

    image_sets = [list_images(folder) for folder in source_paths]
    all_files = set.union(*image_sets) if image_sets else set()

    if not all_files:
        print("Nebyly nalezeny zadne obrazky ve vstupnich slozkach.")
        return

    for filename in sorted(all_files):
        image_paths = [
            (folder / filename) if (folder / filename).exists() else None
            for folder in source_paths
        ]
        build_comparison_image(image_paths, SOURCE_FOLDERS, output_path / filename)

    print(f"Hotovo. Vytvoreno {len(all_files)} porovnani ve slozce: {output_path}")


if __name__ == "__main__":
    main()
