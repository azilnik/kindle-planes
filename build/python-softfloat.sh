#!/bin/sh
# Python 3.12 for Kindles on firmware below 5.16.3 (a PW2), built from source because no
# prebuilt one starts there. Their kernel (3.0.35 on a PW2) predates the helper that
# armel toolchains call for 64-bit atomics, and every python-build-standalone soft-float
# build calls it: "A newer kernel is required to run this binary (__kernel_cmpxchg64)".
# Compiled for ARMv7, those atomics are plain ldrexd/strexd instructions and need nothing
# from the kernel. softfp keeps the soft-float calling convention the Kindle's libraries
# use while still doing the arithmetic on its VFP unit.
#
# Runs in Debian jessie armel, emulated (a couple of hours), so it links against a glibc
# no newer than the Kindle's 2.20. zlib and OpenSSL are built in statically.
# Usage: build/python-softfloat.sh  ->  out/py-soft/py312.tgz, then FLOAT=soft build/bundle.sh
set -e
PY_VER=3.12.14 SSL_VER=3.0.22 ZLIB_VER=1.3.2
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/../out/py-soft"
mkdir -p "$WORK/src"
cd "$WORK/src"
[ -f Python-$PY_VER.tgz ] || {
    curl -fsSLO https://www.python.org/ftp/python/$PY_VER/Python-$PY_VER.tgz
    curl -fsSLO https://www.python.org/ftp/python/$PY_VER/Python-$PY_VER.tgz.sigstore
}
uvx -q sigstore verify identity --bundle Python-$PY_VER.tgz.sigstore \
    --cert-identity thomas@python.org --cert-oidc-issuer https://accounts.google.com Python-$PY_VER.tgz
[ -f openssl-$SSL_VER.tar.gz ] || {
    curl -fsSLO https://github.com/openssl/openssl/releases/download/openssl-$SSL_VER/openssl-$SSL_VER.tar.gz
    curl -fsSLO https://github.com/openssl/openssl/releases/download/openssl-$SSL_VER/openssl-$SSL_VER.tar.gz.sha256
}
awk '{print $1 "  openssl-'$SSL_VER'.tar.gz"}' openssl-$SSL_VER.tar.gz.sha256 | shasum -a 256 -c -
[ -f zlib-$ZLIB_VER.tar.gz ] || curl -fsSLO https://github.com/madler/zlib/releases/download/v$ZLIB_VER/zlib-$ZLIB_VER.tar.gz
echo "bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16  zlib-$ZLIB_VER.tar.gz" | shasum -a 256 -c -

docker pull -q --platform linux/arm/v5 debian/eol:jessie >/dev/null
docker run --rm --platform linux/arm/v5 -v "$WORK":/work debian/eol:jessie sh -c '
set -ex
apt-get -o Acquire::Check-Valid-Until=false -o APT::Get::AllowUnauthenticated=true update -qq
apt-get install -y -qq --force-yes gcc make perl libc6-dev pkg-config xz-utils >/dev/null
export CFLAGS="-march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp -O2"
J=$(nproc)
cd /tmp
tar xzf /work/src/zlib-'$ZLIB_VER'.tar.gz && cd zlib-'$ZLIB_VER'
./configure --static --prefix=/opt/deps >/dev/null && make -j$J >/dev/null && make install >/dev/null
cd /tmp
tar xzf /work/src/openssl-'$SSL_VER'.tar.gz && cd openssl-'$SSL_VER'
./Configure linux-armv4 $CFLAGS no-shared no-tests no-module --prefix=/opt/deps --libdir=lib >/dev/null
make -j$J build_libs >/dev/null && make install_dev >/dev/null
cd /tmp
tar xzf /work/src/Python-'$PY_VER'.tgz && cd Python-'$PY_VER'
CPPFLAGS=-I/opt/deps/include LDFLAGS=-L/opt/deps/lib ./configure --prefix=/opt/python \
    --disable-shared --with-openssl=/opt/deps --with-ensurepip=install >/dev/null
make -j$J >/dev/null 2>/tmp/make.err || { tail -40 /tmp/make.err; exit 1; }
make install >/dev/null 2>&1
/opt/python/bin/python3.12 -c "import ssl, zlib, json, hashlib, socket; print(ssl.OPENSSL_VERSION)"
if grep -rl __kernel_cmpxchg64 /opt/python/bin /opt/python/lib; then
    echo "still needs the kernel helper"; exit 1
fi
cd /opt && tar czf /work/py312.tgz python
'
ls -l "$WORK/py312.tgz"
