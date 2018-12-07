#!/bin/bash

if [[ "$#" -ne 4 ]]; then
    echo "Wrong number of arguments"
    exit 1
fi
D=$1
PREFIX=$2
DESTLIB=$3
DESTSHARE=$4
PIXMAP="${PREFIX}/share/pixmaps/moneyguru.png"

install -D run.py "${D}${DESTLIB}/run.py"
mkdir -p "${D}${PREFIX}/bin"
ln -sf "${DESTLIB}/run.py" "${D}${PREFIX}/bin/moneyguru"
cp -rf hscommon core qt "${D}${DESTLIB}"
mkdir -p "${D}${PREFIX}/share/applications"
install -D -m644 support/moneyguru.desktop \
    "${D}${PREFIX}/share/applications/moneyguru.desktop"
sed -i -e 's#@ICON@#${PIXMAP}#' \
    "${D}${PREFIX}/share/applications/moneyguru.desktop"
install -D -m644 images/logo_big.png "${D}${PIXMAP}"
find locale -name *.mo -exec install -D {} "${D}${DESTSHARE}/{}" \;
