import argparse
import datetime
import logging
import os
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import ffmpeg
from PIL import Image
from pillow_heif import register_heif_opener
from tqdm import tqdm

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".heic", ".cr2", ".png"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov"})
ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

DATE_FORMAT = "%Y-%m-%d %H.%M.%S"


def _parse_creation_time(dt_str):
    return datetime.datetime.fromisoformat(dt_str.rstrip("Z"))


def get_video_creation_time(file_path):
    try:
        streams = ffmpeg.probe(file_path)["streams"]
    except Exception:
        return None
    return next(
        (
            _parse_creation_time(v["tags"]["creation_time"])
            for v in streams
            if "tags" in v and "creation_time" in v["tags"]
        ),
        None,
    )


def get_image_exif_datetime(file_path, verbose):
    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            dt_str = exif.get(0x0132)  # DateTime
            make = exif.get(0x010F)    # Make
            model = exif.get(0x0110)   # Model

            if dt_str:
                dt_obj = datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                new_name = dt_obj.strftime(DATE_FORMAT)
            else:
                if verbose:
                    logging.warning(f"    Cannot find DateTime in EXIF for {file_path}")
                new_name = None

            if new_name and make and model:
                make = make.replace(" ", "_")
                model = model.replace(" ", "_")
                new_name += f" {make}_{model}"
            return new_name
    except Exception as e:
        logging.warning(f"    Error reading EXIF from {file_path}: {e}")
        return None


def get_file_fallback_time(file_path):
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
    ctime = datetime.datetime.fromtimestamp(os.path.getctime(file_path))
    return min(ctime, mtime).strftime(DATE_FORMAT)


def sanitize_filename(new_name):
    new_name = new_name.replace("\x00", "")
    new_name = new_name.replace("/", "_")
    new_name = new_name.replace("Canon_Canon_", "Canon_")
    new_name = new_name.replace("OnePlus_ONEPLUS_", "OnePlus_")
    new_name = new_name.replace("OLYMPUS_CORPORATION_", "OLYMPUS_")
    new_name = new_name.replace("CASIO_COMPUTER_CO.,LTD__", "CASIO_")
    new_name = new_name.replace("PENTAX_Corporation_PENTAX_", "PENTAX_")
    new_name = new_name.replace("NIKON_CORPORATION_NIKON_", "NIKON_")
    return new_name


def scan_dir(directory, verbose):
    file_list = [
        f
        for f in os.listdir(directory)
        if os.path.splitext(f)[1].lower() in ALL_EXTENSIONS
    ]
    if not file_list:
        return

    output_path = os.path.join(directory, "renamed")
    os.makedirs(output_path, exist_ok=True)

    log_lock = threading.Lock()
    claimed_names = set()
    max_workers = min(os.cpu_count() or 1, 8)
    count = 0
    skipped = 0
    rename_history = []

    def _extract_metadata(file):
        """Extract new name from metadata; runs in thread pool."""
        _, extension = os.path.splitext(file)
        source_path = os.path.join(directory, file)
        new_name = None
        if extension.lower() in VIDEO_EXTENSIONS:
            creation_time = get_video_creation_time(source_path)
            if creation_time:
                new_name = creation_time.strftime(DATE_FORMAT)
        elif extension.lower() in IMAGE_EXTENSIONS:
            new_name = get_image_exif_datetime(source_path, verbose)
        if new_name:
            new_name = sanitize_filename(new_name)
        else:
            if verbose:
                with log_lock:
                    logging.warning(
                        f"    [{file}] Cannot get creation time from exif. "
                        "Using file modification/creation time..."
                    )
            new_name = get_file_fallback_time(source_path)
        return file, new_name, extension

    # Phase 1: extract metadata in parallel
    metadata_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_extract_metadata, f): f for f in file_list}
        with tqdm(
            total=len(file_list),
            desc="Processing",
            ascii=True,
            unit="file",
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}",
        ) as pbar:
            for future in as_completed(futures):
                try:
                    metadata_results.append(future.result())
                except Exception as e:
                    skipped += 1
                    with log_lock:
                        logging.error(f"    Error processing {futures[future]}: {e}")
                finally:
                    pbar.update(1)

    # Phase 2: rename sequentially to avoid TOCTOU races
    for file, new_name, extension in metadata_results:
        new_file = new_name + extension
        if file == new_file:
            skipped += 1
            continue
        dup_count = 0
        dst = os.path.join(output_path, new_file)
        while os.path.exists(dst) or dst in claimed_names:
            dup_count += 1
            dst = os.path.join(output_path, f"{new_name}-{dup_count}{extension}")
        claimed_names.add(dst)
        source_path = os.path.join(directory, file)
        try:
            shutil.move(source_path, dst)
        except OSError as e:
            logging.error(f"    Error renaming {file} to {os.path.basename(dst)}: {e}")
            skipped += 1
            continue
        rename_history.append((file, os.path.basename(dst)))
        count += 1

    if rename_history:
        logging.info("\nRename History:")
        max_len = max(len(orig) for orig, _ in rename_history)
        for orig, renamed in rename_history:
            logging.info(f"    {orig:<{max_len}} => {renamed}")
    else:
        logging.info("\nNo files needed renaming in this directory.")
    logging.info(f"\nFinished processing {directory}. Renamed: {count}, Skipped/Errors: {skipped}")


def main():
    parser = argparse.ArgumentParser(
        description="Rename image and video files based on EXIF/metadata creation time."
    )
    parser.add_argument("-p", "--path", required=True, help="Directory path to scan for files.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging for debugging.")
    args = parser.parse_args()

    path = args.path
    verbose = args.verbose

    if not os.path.isdir(path):
        print(f"Error: Path '{path}' is not a valid directory.")
        sys.exit(1)

    current_ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    log_file_name = f"rename_{current_ts}.log"
    log_file_path = os.path.join(os.path.dirname(__file__) or '.', log_file_name)

    log_level = logging.DEBUG if verbose else logging.INFO
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    logging.info(f"Starting scan in directory: {path}")
    logging.info(f"Log file: {log_file_path}")

    register_heif_opener()

    for root, dirs, files in os.walk(path, topdown=True):
        if 'renamed' in dirs:
            dirs.remove('renamed')
        if os.path.basename(root) == 'renamed' and os.path.dirname(root) == path:
            continue
        logging.info(f"Scanning {root}...")
        scan_dir(root, verbose)
        logging.info(f"Finished scanning {root}.")
        logging.info("")

    logging.info("Scan complete.")


if __name__ == "__main__":
    main()
