#!/usr/bin/env bash
# Package both Lambdas into build/. Terraform zips these folders on `terraform apply`.
#   build/lambda   transform (our code + openpyxl)
#   build/analyst  AI analyst (our code only; boto3 is built into Lambda)
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build/lambda build/analyst
mkdir -p build/lambda build/analyst
# Install for Lambda's Linux, not your Mac. openpyxl is pure Python, so this is safe anywhere.
python3 -m pip install --quiet \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 \
  -r src/transform/requirements.txt -t build/lambda
cp src/transform/*.py build/lambda/
cp src/analyst/*.py src/analyst/page.html build/analyst/
echo "Built build/lambda ($(du -sh build/lambda | cut -f1)) and build/analyst ($(du -sh build/analyst | cut -f1))"
