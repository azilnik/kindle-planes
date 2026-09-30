set -ex
apt-get -o Acquire::Check-Valid-Until=false -o APT::Get::AllowUnauthenticated=true update -qq
apt-get install -y -qq --force-yes gcc libc6-dev libfreetype6-dev zlib1g-dev pkg-config >/dev/null
ldd --version | head -1
mkdir -p /opt && tar xzf /work/py312.tgz -C /opt
PY=/opt/python/bin/python3.12
$PY -m pip -q install --upgrade pip wheel setuptools
cd /work
CFLAGS="-std=gnu99" $PY -m pip wheel --no-deps --no-binary :all: -w /work/wheels "pillow==11.3.0" -C jpeg=disable -C tiff=disable -C lcms=disable -C webp=disable -C jpeg2000=disable -C imagequant=disable -C xcb=disable -C raqm=disable -C avif=disable 2>&1 | tail -20
$PY -m pip download --no-deps -d /work/wheels requests urllib3 idna certifi charset-normalizer --only-binary :all: --platform any -q || $PY -m pip download --no-deps -d /work/wheels requests urllib3 idna certifi -q
ls -la /work/wheels
