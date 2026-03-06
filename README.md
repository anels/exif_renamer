# exif_renamer

基于 EXIF/元数据的时间批量重命名图片和视频文件。

## 使用 uv 进行依赖与运行

前置：安装 uv（Windows PowerShell）

```
iwr https://astral.sh/uv/install.ps1 | iex
```

初始化并安装依赖（会生成/更新 `.venv` 和 `uv.lock`）：

```
uv sync
```

运行命令行工具：

```
uv run exif-renamer -p <目录路径> [-v]
```

或直接运行脚本：

```
uv run python rename.py -p <目录路径> [-v]
```

开发工具（可选）：

```
uv run flake8
```

项目依赖已迁移至 `pyproject.toml`，`uv` 将以此为准管理环境与锁定文件。
Rename Photo and Video based on EXIF info

## install

First install ffmpeg
```
scoop install ffmpeg
```

Then install requirements
```
virtualenv .
.\Scripts\activate
pip install -r requirements.txt
```

## run
```
python .\rename.py -p 'D:\OneDrive\Pictures\Camera Roll\2022'
```

## 简介
exif_renamer 是一个用于批量重命名照片和视频文件的工具，依据文件的 EXIF 信息或创建时间自动生成规范化文件名。

## 使用方法

### 依赖环境
- Python 3.x
- 依赖库：ffmpeg、Pillow、pillow_heif

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行示例
```bash
python .\rename.py -p 'D:\OneDrive\Pictures\Camera Roll\2022'
```

### 参数说明
- `-p` 或 `--path`：必填，指定需要重命名的目录路径。
- `-v` 或 `--verbose`：可选，输出详细日志信息。
- `-h`：显示帮助信息。

### 功能说明
- 支持 jpg、jpeg、heic、cr2、png、mp4、mov 等常见图片和视频格式。
- 优先使用 EXIF 或视频元数据中的拍摄时间，若无则使用文件创建/修改时间。
- 自动将重命名后的文件保存到原目录下的 renamed 子文件夹中。
- 遇到同名文件自动追加序号避免覆盖。

### 示例
```bash
python rename.py -p "./test_photos" -v
```