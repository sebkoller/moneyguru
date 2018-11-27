#!/bin/bash

function mergeall() {
    for pot in *.pot; do
        echo "Merging $pot"
        po=${pot%.pot}.po
        find . -name ${po} -exec msgmerge -U --backup=off {} ${pot} \;
    done
}

for subdir in locale qtlib/locale; do
    echo "Entering $subdir"
    ( cd $subdir; mergeall )
done
