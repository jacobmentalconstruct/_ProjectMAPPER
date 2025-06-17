#!/bin/bash
echo "============================"
echo " Launching ProjectMAPPER   "
echo "============================"

# Activate conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate mindshard

# Run the script from new location
python src/projectmapper/main.py
