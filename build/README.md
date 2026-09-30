# build

Two scripts from setting up the Kindle, kept for the next one. Steps in
[docs/device-setup.md](../docs/device-setup.md).

- `install-ssh.sh`: a KUAL scriptlet. Installs USBNetLite (dropbear) from
  `/mnt/us/claude-bootstrap/` with key-only root login over Wi-Fi, started at boot.
- `pillow-armhf.sh`: builds Pillow 11.3 and downloads `requests` wheels for the Kindle's
  Python 3.12, inside a Debian jessie armv7 container so the result links against a glibc
  older than the Kindle's.
