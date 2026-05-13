#!/usr/bin/env bash
set -e

# Install WeasyPrint system dependencies (Render uses Ubuntu/Debian)
apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libharfbuzz0b \
    libfontconfig1 \
    shared-mime-info \
    2>/dev/null || echo "apt-get failed, continuing without system deps (PDF export will be unavailable)"

pip install -r requirements.txt
