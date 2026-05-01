# Clipboard Sync Linux Requirements

`Clipboard Sync` requires one of the following Linux clipboard backends:

- `xclip` and `xsel` for X11-based desktops
- `wl-clipboard` for Wayland-based desktops

Suggested use:

- X11 desktops: install `xclip`; use `xsel` only if `xclip` is unavailable.
- Wayland desktops: install `wl-clipboard`.
- Mixed or unknown environments: install at least one X11 backend and one Wayland backend.

Quick install:

- Debian / Ubuntu:
  - `sudo apt install xclip xsel wl-clipboard`
- Fedora:
  - `sudo dnf install xclip xsel wl-clipboard`
- Arch Linux:
  - `sudo pacman -S xclip xsel wl-clipboard`
- openSUSE:
  - `sudo zypper install xclip xsel wl-clipboard`