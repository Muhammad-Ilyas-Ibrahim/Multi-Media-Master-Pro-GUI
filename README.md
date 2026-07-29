# Multi-Media-Master-Pro GUI - User Guide

## 📋 Table of Contents
- [Overview](#overview)
- [Features](#features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Building from Source](#building-from-source)
- [Usage Guide](#usage-guide)

## Overview

Multi-Media-Master-Pro is a professional, feature-rich GUI application for multimedia processing. Built with PyQt5, it provides an intuitive interface for video compression, image compression, audio extraction, format conversion, and screen recording.

## Features

### Core Functionality
- **Video Compression**: Compress single videos or batch process multiple videos with three compression levels
- **Image Compression**: Compress single images or batch process with quality control
- **Audio Extraction**: Extract audio from video files in multiple formats (MP3, WAV, AAC, FLAC, OGG)
- **Audio Conversion**: Convert audio files between different formats
- **Image Conversion**: Convert images between different formats (JPG, PNG, BMP, GIF, WEBP, TIFF)
- **Screen Recording**: Record your screen with FFmpeg

### Advanced Features
- **Three Compression Levels**: 
  - Low: Best quality, larger file size (CRF 20 for video, Quality 95 for images)
  - Medium: Balanced quality and size (CRF 25 for video, Quality 85 for images)
  - High: Maximum compression, smaller file size (CRF 30 for video, Quality 70 for images)
- **Real-time Progress Tracking**: Visual progress bars and status updates
- **Operation Cancellation**: Stop long-running tasks at any time
- **Batch Processing**: Process multiple files in a directory at once
- **Format Conversion**: Change file extensions during compression
- **Size Reporting**: Detailed file size reduction statistics
- **CSV Reports**: Batch operations generate CSV files with compression statistics

## System Requirements

### Minimum Requirements
- **Operating System**: Windows 7 or later (64-bit recommended)
- **RAM**: 2 GB minimum, 4 GB recommended
- **Storage**: 500 MB free space
- **FFmpeg**: Must be available (included in distribution or separate installation)

### Python Requirements (for building from source)
- **Python**: 3.6 or higher
- **PyQt5**: 5.15.0 or higher
- **PyInstaller**: For building executables (optional)

## Installation

### Option 1: Using the Installer (Recommended)

1. Download the latest installer (`MultiMediaMasterPro-GUI-Setup-vX.Y.exe`) from the [Releases page](https://github.com/Muhammad-Ilyas-Ibrahim/Multi-Media-Master-Pro-GUI/releases)
2. Run the installer and follow the on-screen prompts
3. Launch **Multi-Media-Master-Pro** from the Start Menu or the desktop shortcut

> FFmpeg is bundled with the installer — no separate setup required.

### Option 2: Running from Source

1. **Install Python 3.6+** from [python.org](https://www.python.org/downloads/)

2. **Clone the repository**:
   ```bash
   git clone https://github.com/Muhammad-Ilyas-Ibrahim/Multi-Media-Master-Pro-GUI.git
   cd Multi-Media-Master-Pro-GUI
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install FFmpeg**:
   - `ffmpeg.exe` is already included in the repository (via Git LFS).
   - If it is missing, download it from [ffmpeg.org](https://ffmpeg.org/download.html) and place `ffmpeg.exe` in the project root, or add it to your PATH.

5. **Run the Application**:
   ```bash
   python main.py
   ```

## Building from Source

### Prerequisites
- Python 3.6 or higher
- PyInstaller (will be installed automatically by build script)
- icon.ico file (optional, for custom icon)

### Building the Executable

1. **Using the Build Script (Recommended)**:
   ```bash
   build.bat
   ```
   This script will:
   - Check Python installation
   - Install PyInstaller if needed
   - Build the executable with icon support
   - Include ffmpeg.exe in the distribution

2. **Manual Build**:
   ```bash
   pip install pyinstaller
   pyinstaller --name=MultiMediaMasterPro --onedir --windowed --noconsole --icon=icon.ico ^
       --add-data "ffmpeg.exe;." --collect-all PyQt5 --collect-all qtawesome ^
       --hidden-import=PyQt5.QtMultimedia --hidden-import=PyQt5.QtMultimediaWidgets main.py
   ```

3. **Output Location**:
   - The application is built to `dist\MultiMediaMasterPro\` (one-folder build)
   - `ffmpeg.exe` is bundled into that folder automatically

## Usage Guide

### Video Compression

1. Navigate to the **"🎥 Video Compression"** tab
2. Click **"📁 Browse"** to select a video file
3. Choose compression level:
   - **Low**: Best quality (CRF 20, Audio 128k)
   - **Medium**: Balanced (CRF 25, Audio 96k) - *Recommended*
   - **High**: Maximum compression (CRF 30, Audio 64k)
4. (Optional) Check **"Change file extension"** to convert format
5. Click **"🚀 Compress Video"**
6. Monitor progress in the progress bar
7. Results show original size, compressed size, and reduction percentage

### Batch Video Compression

1. Go to **"📂 Batch Video Compression"** tab
2. Select a directory containing video files
3. Choose compression level and format options
4. Click **"🚀 Compress All Videos"**
5. Compressed files will be saved in a `_compressed` subdirectory
6. A CSV report (`compression_data.csv`) will be generated with statistics

### Image Compression

1. Navigate to **"🖼️ Image Compression"** tab
2. Select an image file
3. Choose compression level:
   - **Low**: Quality 95
   - **Medium**: Quality 85 - *Recommended*
   - **High**: Quality 70
4. (Optional) Change file extension
5. Click **"🚀 Compress Image"**

### Audio Extraction

1. Go to **"🎵 Audio Extraction"** tab
2. Select a video file
3. Choose output format (MP3, WAV, AAC, FLAC, OGG)
4. Click **"🎵 Extract Audio"**
5. Audio file will be saved in the same directory as the video

### Audio Conversion

1. Navigate to **"🔄 Audio Conversion"** tab
2. Choose **Single File** or **Directory**
3. Select file/directory
4. Choose target format
5. Click **"🔄 Convert Audio"**

### Image Conversion

1. Go to **"🖼️ Image Conversion"** tab
2. Choose **Single File** or **Directory**
3. Select file/directory
4. Choose target format
5. Click **"🖼️ Convert Images"**

### Screen Recording

1. Navigate to **"🎬 Screen Recording"** tab
2. Select output directory for recordings
3. Click **"🔴 Start Recording"**
4. Click **"⏹️ Stop Recording"** when done
5. Recording will be saved with timestamp in filename

## File Structure

```
Multi-Media-Master-Pro-GUI/
├── main.py                     # Entry point (run this)
├── mediamaster/                # Application package
│   ├── core/                   # Backend layer
│   │   ├── config.py           # Constants, paths, FFmpeg discovery, helpers
│   │   └── worker.py           # Background FFmpeg thread (all tasks)
│   └── ui/                     # Presentation layer
│       ├── icons.py            # Font Awesome icon helpers
│       ├── theme.py            # Light/dark palettes + stylesheet
│       ├── widgets.py          # Reusable form widgets
│       ├── timeline.py         # Scrubbable trim timeline
│       ├── trim_studio.py      # Media-player trim page
│       └── main_window.py      # Main window
├── build.bat                   # Local build script
├── icon.ico                    # Application icon
├── ffmpeg.exe                  # FFmpeg binary (bundled via Git LFS)
├── requirements.txt            # Python dependencies
├── README.md                   # This file
└── .github/workflows/          # CI: builds the exe + installer and publishes a release
```

## License

This project is licensed under the **MIT License**.

See the [LICENSE](LICENSE) file for more information.

## Contributing

Contributions are welcome! 

The **Audio/Video Trimming** feature is still being improved and contributions related to its functionality, performance and usability are especially appreciated.

Feel free to open an issue or submit a pull request.
