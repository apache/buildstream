#!/bin/bash

TMP_DIR=tmp

REPO=`pwd`/$TMP_DIR/repo
DATA_DIR=$TMP_DIR/files

# Make sure this is only ran once
if [ ! -d "$REPO" ]; then
    mkdir -p $REPO
    mkdir -p $DATA_DIR

    ostree --repo=$REPO init --mode=archive-z2

    cd $DATA_DIR

    # Do first commit
    # 3c11e7aed983ad03a2982c33f061908879033dadce4c21ce93243c118264ee0f
    echo "1" > foo
    ostree --repo=$REPO commit --branch=my-branch --subject="Initial commit" --body="This is the first commit."

    # Second commit
    # 85a4d86655f56715aea16170a0599218f8f42a8efea4727deb101b1520325f7e
    rm foo
    echo "1" > bar
    ostree --repo=$REPO commit --branch=my-branch --subject="Another commit" --body="Removing foo and adding bar"
fi