#!/usr/bin/env bash

for i in /proc/[0-9]*/cmdline; do
    pid_=$(basename $(dirname "$i"))
    cmdline=$(cat $i | tr '\000' ' ')
    if [[ $cmdline == "python"*"miso.run"* ]]; then
        echo "kill -9 $pid_ ($(echo $cmdline)"
        kill -9 $pid_
        exit $?
    fi
done
