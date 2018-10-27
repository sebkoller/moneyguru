#!/bin/bash

echo "Creating git archive"
version=`python3 -c "from core.app import Application; print(Application.VERSION)"`
dest="moneyguru-src-${version}.tar"

git archive -o ${dest} HEAD

# Now, we need to include submodules
submodules="hscommon qtlib"

for submodule in $submodules; do
    echo "Adding submodule ${submodule} to archive"
    archive_name="${submodule}.tar"
    git -C ${submodule} archive -o ../${archive_name} --prefix ${submodule}/ HEAD
    tar -A ${archive_name} -f ${dest}
    rm ${archive_name}
done

gzip -f ${dest}
echo "Built source package ${dest}.gz"
