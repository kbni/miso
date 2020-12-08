#!/usr/bin/env bash

while :; do
    echo "> $@"
    "$@"
    sleep 1 && echo "."
    sleep 1 && echo "."
    sleep 1 && echo "."
done

exit 0
