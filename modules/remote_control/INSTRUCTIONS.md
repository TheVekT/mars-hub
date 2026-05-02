# Remote Control FFmpeg Requirements

`Remote Control` requires `ffmpeg` for media streaming and screen capture capabilities.

Suggested use:

- Install the latest stable version of `ffmpeg` available for your platform.
- Ensure `ffmpeg` is available in your system PATH.

Quick install:

**Windows:**
  - Using Chocolatey: `choco install ffmpeg`
  - Using Winget: `winget install FFmpeg.FFmpeg`
  - Manual: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

**Linux:**
  - Debian / Ubuntu: `sudo apt install ffmpeg`
  - Fedora: `sudo dnf install ffmpeg`
  - Arch Linux: `sudo pacman -S ffmpeg`
  - openSUSE: `sudo zypper install ffmpeg`

After installation, verify that `ffmpeg` is properly installed by running:
```
ffmpeg -version
```
