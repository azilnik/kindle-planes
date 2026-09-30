#!/bin/sh
# SSH for Kindles on firmware below 5.16.3 (a PW2 tops out at 5.12), where USBNetLite's
# hard-float dropbear can't run. Builds dropbear from its author's source as one static
# soft-float binary, so it doesn't care what libraries the Kindle has. Needs Docker; Zig
# does the cross-compiling in a native container, which takes a couple of minutes.
# Usage: build/dropbear.sh VERSION   (e.g. 2026.94)  ->  out/dropbear/dropbearmulti
set -e
VER=${1:?usage: dropbear.sh VERSION}
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/../out/dropbear"
TARBALL=dropbear-$VER.tar.bz2
mkdir -p "$WORK/zigcache"
cd "$WORK"
if [ ! -f "$TARBALL" ]; then
    curl -fsSL -O "https://matt.ucc.asn.au/dropbear/releases/$TARBALL"
    curl -fsSL -o SHA256SUM.asc https://matt.ucc.asn.au/dropbear/releases/SHA256SUM.asc
    # The author's checksum list; its signature is his GPG key, see the releases page
    grep " $TARBALL\$" SHA256SUM.asc | shasum -a 256 -c -
fi

# --platform: Docker keeps one platform per tag, and an emulated build takes an hour
docker pull -q --platform linux/arm64 debian:bookworm-slim >/dev/null
docker run --rm --platform linux/arm64 -v "$WORK":/work -e ZIG_GLOBAL_CACHE_DIR=/work/zigcache \
    debian:bookworm-slim sh -c '
set -e
apt-get update -qq >/dev/null && apt-get install -y -qq make bzip2 llvm python3-venv >/dev/null 2>&1
python3 -m venv /z && /z/bin/pip -q install ziglang
# musleabi: soft-float calling convention, static musl, so getpwnam reads /etc/passwd itself
printf "#!/bin/sh\nexec /z/bin/python -m ziglang cc -target arm-linux-musleabi -mcpu=cortex_a9 \"\$@\"\n" >/usr/local/bin/kcc
chmod +x /usr/local/bin/kcc
cd /tmp && tar xjf /work/'"$TARBALL"' && cd dropbear-'"$VER"'
CC=kcc AR="/z/bin/python -m ziglang ar" RANLIB="/z/bin/python -m ziglang ranlib" \
    ./configure --host=arm-linux-musleabi --disable-zlib --enable-static \
    --disable-lastlog --disable-utmp --disable-utmpx --disable-wtmp --disable-wtmpx \
    --disable-pututline --disable-pututxline >/tmp/configure.log 2>&1 || { tail -30 /tmp/configure.log; exit 1; }
make -j8 PROGRAMS="dropbear dropbearkey scp" STATIC=1 MULTI=1 >/tmp/make.log 2>&1 || { grep -iE "error|undefined" /tmp/make.log | head -30; exit 1; }
llvm-strip dropbearmulti
llvm-readelf -h dropbearmulti | grep Flags  # 0x5000200: EABI5, soft-float
cp dropbearmulti /work/
'
ls -l "$WORK/dropbearmulti"
