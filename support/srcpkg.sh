#!/bin/bash

echo "Creating git archive"
version=`python3 -c "from core import __version__; print(__version__)"`
dest="moneyguru-src-${version}.tar"

git archive -o ${dest} HEAD
gzip -f ${dest}
echo "Built source package ${dest}.gz"
