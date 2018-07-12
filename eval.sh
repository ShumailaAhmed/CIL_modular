#!/usr/bin/env bash

export CUDA_VISIBLE_DEVICES=2
ulimit -Sn 60000

python \
drive_interfaces/carla/comercial_cars/run_test_cvpr.py \
-e mm45_rc28_wpz_M_mm41_cityscapes_aug_cluster \
-s results/mm45_rc28_wpz_M_mm41_cityscapes_aug_cluster \
-l 127.0.0.1 \
-p 2000 \
-t 2 \
-cy carla_0 \
-w 1 \
-m 0.25 || true #TestTownTrainWeather