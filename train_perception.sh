#!/usr/bin/env bash

export CUDA_VISIBLE_DEVICES=3
ulimit -Sn 600000
python chauffeur.py train \
    -e mm45_v4_PcSensordropLessmap_rfsv45_extra_structure_noise_nocolor_shoulder \
    -m 0.05
