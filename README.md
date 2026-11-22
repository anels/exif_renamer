# exif_renamer

基于 EXIF/元数据的拍摄时间，批量重命名照片和视频文件。

## 功能

- 支持 jpg、jpeg、heic、cr2、png、mp4、mov。
- 照片优先使用 EXIF `DateTimeOriginal`，其次 `DateTime`；有相机厂商和型号时追加到文件名。
- 视频使用 ffprobe 读到的 `creation_time`，并转换为本机时区。
- 读不到元数据时，回退到文件创建/修改时间中较早的一个。
- 文件被**移动**到原目录下的 `renamed` 子文件夹，子目录会递归处理。
- 同名文件按原文件名顺序追加 `-1`、`-2` 序号，避免覆盖。
- 每次移动都会立即写入日志 `rename_<时间戳>.log`（位于脚本所在目录），这是原文件名的唯一记录。

文件名格式：`2024-06-01 12.00.00 Canon_EOS_R5.jpg`

## 安装

需要 [uv](https://docs.astral.sh/uv/) 和 ffmpeg（Windows）：

```
scoop install uv ffmpeg
uv sync
```

## 使用

```
uv run exif-renamer -p <目录路径> [-v]
```

- `-p` / `--path`：必填，要处理的目录。
- `-v` / `--verbose`：输出详细日志。

## 开发

```
uv run python -m unittest discover -s tests -t .
uv run --extra dev flake8
```

## 时区说明

视频的 `creation_time` 通过 `astimezone()` 转成运行本工具的机器的时区。在其他时区拍摄的视频会按处理机器的时区命名，而不是拍摄地时区。
