#!/usr/bin/env bash
# This is the shell script equivalent of the pm.bat file.

# === CONFIG ===
MAIN_SCRIPT="_ProjectMAPPER.py"

# === RUN ===
echo "[🚀] Running ${MAIN_SCRIPT}..."
# Use python3, as 'python' can be ambiguous on Mac/Linux.
python3 "${MAIN_SCRIPT}"

echo "[🧹] Done."
# This will wait for the user to press a key before the terminal closes.
read -p "Press [Enter] to continue..."