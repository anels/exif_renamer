import datetime
import getopt
import logging
import os
import sys

import ffmpeg
from PIL import Image
from PIL.ExifTags import TAGS
from pillow_heif import register_heif_opener

directory = './'
image_extensions = (['.jpg', '.jpeg', '.heic', '.cr2', '.png'])
video_extensions = (['.mp4', '.mov'])


def scanDir(directory, verbose):

    filelist = [f for f in os.listdir(directory) if os.path.splitext(
        f)[1].lower() in (video_extensions + image_extensions)]
    register_heif_opener()

    count = 0

    def gt(dt_str):
        dt, _, us = dt_str.partition(".")
        dt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
        us = int(us.rstrip("Z"), 10)
        return dt + datetime.timedelta(microseconds=us)

    for i, file in enumerate(filelist):
        logging.info(f"Processing ({i+1}/{len(filelist)}) {file}...")
        filename, extension = os.path.splitext(file)
        Filename = os.path.join(directory, file)

        new_name = None

        if (extension.lower() in video_extensions):
            video = ffmpeg.probe(Filename)["streams"]
            # logging.info(video)
            if format_time := next((gt(v["tags"]["creation_time"]) for v in video if "creation_time" in v["tags"]), None):
                format_time_string = format_time.strftime("%Y-%m-%d %H.%M.%S")
                new_name = format_time_string.strip()

        if (extension.lower() in image_extensions):
            with Image.open(Filename) as img:
                exif_table = {}
            try:
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
                        logging.warn(
                            f"    Cannot find datetime in exif. Available attributes: {exif_table}")

                make = model = None

                if "Make" in exif_table:
                    make = exif_table["Make"]
                if "Model" in exif_table:
                    model = exif_table["Model"]

                if new_name and make and model:
                    make = make.replace(" ", "_")
                    model = model.replace(" ", "_")
                    new_name += f" {make}_{model}"
            except Exception as e:
                if verbose:
                    logging.error(f"    Something went wrong. Exception: {e}")

        if new_name:
            new_name = new_name.replace('\x00', '')
            new_name = new_name.replace('/', '_')
            new_name = new_name.replace('Canon_Canon_', 'Canon_')
            new_name = new_name.replace('OnePlus_ONEPLUS_', 'OnePlus_')
            new_name = new_name.replace('OLYMPUS_CORPORATION_', 'OLYMPUS_')
            new_name = new_name.replace('CASIO_COMPUTER_CO.,LTD__', 'CASIO_')
            new_name = new_name.replace(
                'PENTAX_Corporation_PENTAX_', 'PENTAX_')
            new_name = new_name.replace('NIKON_CORPORATION_NIKON_', 'NIKON_')

        else:
            if verbose:
                logging.warn(
                    "    Cannot get creation time from exif. Using file modification/creation time...")
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(Filename))
            ctime = datetime.datetime.fromtimestamp(os.path.getctime(Filename))

            earliest_time = ctime if ctime < mtime else mtime
            format_time_string = earliest_time.strftime("%Y-%m-%d %H.%M.%S")
            # logging.info(format_time_string)
            new_name = format_time_string.strip()

        new_file = (new_name + extension)

        if file != new_file:
            outputPath = os.path.join(directory, "renamed")
            if not os.path.exists(outputPath):
                os.makedirs(outputPath)

            dupCount = 0
            src = os.path.join(directory, file)
            dst = os.path.join(outputPath, new_file)
            while os.path.exists(dst):
                dupCount += 1
                dst = os.path.join(
                    outputPath, f"{new_name}-{dupCount}{extension}")
            os.rename(f"{src}", f"{dst}")
            dupCount = 0

            count = count + 1
            logging.info(f'    Rename: {file.rjust(35)}    =>    {new_file}')
        else:
            logging.info("    File name is already updated.")

    logging.info(f'\nAll done. {str(count)} files are renamed. ')


def main(argv):
    current_file = os.path.basename(__file__)

    usage_msg = f"Usage: {current_file} -p <path> [-v]"

    path = ""
    verbose = False
    try:
        opts, args = getopt.getopt(argv, "hp:", ["path="])
    except getopt.GetoptError:
        print(f"Option error, please try again.\n{usage_msg}")
        sys.exit(2)
    for opt, arg in opts:
        if opt == "-h":
            print(f"Help.\n{usage_msg}")
            sys.exit()
        elif opt in ("-p", "--path"):
            path = arg
        elif opt in ("-v", "--verbose"):
            verbose = arg
    if path == "":
        print(f"Path is missing, please try again.\n{usage_msg}")
        sys.exit(2)

    current_ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    log_file = os.path.join(os.path.dirname(__file__),
                            f"rename_{current_ts}.log")

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    for (root, dirs, files) in os.walk(path, topdown=True):
        if (os.path.basename(root) != "renamed"):
            logging.info(f"Scanning {root}..")
            scanDir(root, verbose)
            logging.info("")


if __name__ == "__main__":
    main(sys.argv[1:])
