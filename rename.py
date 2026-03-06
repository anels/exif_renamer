import datetime
import getopt
import logging
import os
import sys

import ffmpeg
from PIL import Image
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener
from tqdm import tqdm

image_extensions = [".jpg", ".jpeg", ".heic", ".cr2", ".png"]
video_extensions = [".mp4", ".mov"]


def get_video_creation_time(Filename):
    video = ffmpeg.probe(Filename)["streams"]

    def gt(dt_str):
        dt, _, us = dt_str.partition(".")
        dt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
        us = int(us.rstrip("Z"), 10)
        return dt + datetime.timedelta(microseconds=us)

    return next(
        (gt(v["tags"]["creation_time"]) for v in video if "creation_time" in v["tags"]),
        None,
    )


def get_image_exif_datetime(Filename, verbose):
    try:
        with Image.open(Filename) as img:
            exif_table = {}
            for k, v in img.getexif().items():
                tag = TAGS.get(k)
                exif_table[tag] = v
            if "DateTime" in exif_table:
                dt = exif_table["DateTime"]
                day, dtime = dt.split(" ", 1)
                dd = day.replace(":", "-")
                tt = dtime.replace(":", ".")
                new_name = " ".join([dd, tt]).strip()
            else:
                if verbose:
                    logging.warning(
                        f"    Cannot find datetime in exif. Available attributes: {exif_table}"
                    )
                new_name = None
            make = exif_table.get("Make", None)
            model = exif_table.get("Model", None)
            if new_name and make and model:
                make = make.replace(" ", "_")
                model = model.replace(" ", "_")
                new_name += f" {make}_{model}"
            return new_name
    except Exception as e:
        if verbose:
            logging.error(f"    Something went wrong. Exception: {e}")
        return None


def get_file_fallback_time(Filename):
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(Filename))
    ctime = datetime.datetime.fromtimestamp(os.path.getctime(Filename))
    earliest_time = ctime if ctime < mtime else mtime
    return earliest_time.strftime("%Y-%m-%d %H.%M.%S").strip()


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


def scanDir(directory, verbose):
    filelist = [
        f
        for f in os.listdir(directory)
        if os.path.splitext(f)[1].lower() in (video_extensions + image_extensions)
    ]
    if not filelist:
        return
    register_heif_opener()
    outputPath = os.path.join(directory, "renamed")
    if not os.path.exists(outputPath):
        os.makedirs(outputPath)
    count = 0
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    log_lock = threading.Lock()
    max_workers = min(os.cpu_count() or 1, 8)  # Use CPU count, default to 1 if None
    count = 0
    skipped = 0
    rename_history = []

    def process_file(file, current_dir, output_path, log_lock, rename_history_list):
        filename, extension = os.path.splitext(file)
        source_path = os.path.join(current_dir, file)
        new_name = None
        if extension.lower() in video_extensions:
            format_time = get_video_creation_time(source_path)
            if format_time:
                new_name = format_time.strftime("%Y-%m-%d %H.%M.%S").strip()
        elif extension.lower() in image_extensions:
            new_name = get_image_exif_datetime(source_path, verbose)
        if new_name:
            new_name = sanitize_filename(new_name)
        else:
            if verbose:
                with log_lock:
                    logging.warning(
                        f"    [{file}] Cannot get creation time from exif. Using file modification/creation time..."
                    )
            new_name = get_file_fallback_time(source_path)
        new_file = new_name + extension
        if file != new_file:
            dupCount = 0
            dst = os.path.join(output_path, new_file)
            while os.path.exists(dst):
                dupCount += 1
                dst = os.path.join(output_path, f"{new_name}-{dupCount}{extension}")
            try:
                os.rename(source_path, dst)
            except OSError as e:
                with log_lock:
                    logging.error(f"    Error renaming {file} to {os.path.basename(dst)}: {e}")
                return 0 # Indicate failure/skip
            entry = f"{file} => {os.path.basename(dst)}"
            with log_lock:
                rename_history_list.append(entry)
            return 1
        else:
            return 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Pass necessary context to each worker
        futures = {executor.submit(process_file, file, directory, outputPath, log_lock, rename_history): file for file in filelist}

        with tqdm(
            total=len(filelist),
            desc="Processing",
            ascii=True,
            unit="file",
            dynamic_ncols=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}",
        ) as pbar:
            for future in as_completed(futures):
                original_file = futures[future]
                try:
                    result = future.result()
                    if result == 1:
                        count += 1
                    else:
                        # Skipped either because name didn't change or due to rename error
                        skipped += 1
                except Exception as e:
                    skipped += 1 # Count exceptions as skipped
                    with log_lock:
                        logging.error(f"    Error processing file {original_file}: {e}")
                finally:
                    pbar.update(1) # Ensure progress bar updates even on error

    # Log results after processing all files
    if rename_history:
        logging.info("\nRename History:")
        max_len = max(len(entry.split('=>')[0].strip()) for entry in rename_history) if rename_history else 0
        for entry in rename_history:
            original, renamed = entry.split('=>')
            logging.info(f"    {original.strip():<{max_len}} => {renamed.strip()}")
    else:
        logging.info("\nNo files needed renaming in this directory.")
    logging.info(f"\nFinished processing {directory}. Renamed: {count}, Skipped/Errors: {skipped}")


import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Rename image and video files based on EXIF/metadata creation time."
    )
    parser.add_argument(
        "-p",
        "--path",
        required=True,
        help="Directory path to scan for files.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging for debugging.",
    )
    args = parser.parse_args()

    path = args.path
    verbose = args.verbose

    if not os.path.isdir(path):
        print(f"Error: Path '{path}' is not a valid directory.")
        sys.exit(1)

    current_ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    log_file_name = f"rename_{current_ts}.log"
    # Place log file in the script's directory or a dedicated logs folder if preferred
    log_file_path = os.path.join(os.path.dirname(__file__) or '.', log_file_name)

    log_level = logging.DEBUG if verbose else logging.INFO
    # Ensure stdout/stderr use UTF-8 on Windows consoles to avoid cp1252 errors
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
            logging.StreamHandler(sys.stdout)
        ],
        force=True
    )

    logging.info(f"Starting scan in directory: {path}")
    logging.info(f"Log file: {log_file_path}")

    # Walk through directory, skipping the 'renamed' subdirectory
    for root, dirs, files in os.walk(path, topdown=True):
        # Prevent recursion into the 'renamed' directory
        if 'renamed' in dirs:
            dirs.remove('renamed')

        # Skip the root 'renamed' directory if it exists at the top level
        if os.path.basename(root) == 'renamed' and os.path.dirname(root) == path:
             continue

        logging.info(f"Scanning {root}...")
        scanDir(root, verbose)
        logging.info(f"Finished scanning {root}.")
        logging.info("") # Add a blank line for readability

    logging.info("Scan complete.")

if __name__ == "__main__":
    main()
