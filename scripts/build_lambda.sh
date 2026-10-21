#!/usr/bin/env bash
# Package the transform Lambda: our code + openpyxl, in build/lambda/.
# Terraform zips that folder on `terraform apply`.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build/lambda
mkdir -p build/lambda
# Install for Lambda's Linux, not your Mac. openpyxl is pure Python, so this is safe anywhere.
python3 -m pip install --quiet \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 \
  -r src/transform/requirements.txt -t build/lambda
cp src/transform/*.py build/lambda/
echo "Built build/lambda ($(du -sh build/lambda | cut -f1))"
