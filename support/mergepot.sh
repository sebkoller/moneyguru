#!/bin/bash

cd locale
for pot in *.pot; do
    echo "Merging $pot"
    po=${pot%.pot}.po
    find . -name ${po} -exec msgmerge -U --backup=off {} ${pot} \;
done
