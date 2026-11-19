#!/bin/sh
set -eu
pip-audit --disable-pip --require-hashes --progress-spinner off -r infra/web/requirements.txt
