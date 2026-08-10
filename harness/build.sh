#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")"

gcc \
    -g \
    -O0 \
    -Wall \
    -Wextra \
    -fsanitize=address,undefined \
    -I../target/parson \
    harness.c \
    ../target/parson/parson.c \
    -o harness
