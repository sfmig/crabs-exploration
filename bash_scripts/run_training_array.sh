#!/bin/bash

#SBATCH -p gpu # partition
#SBATCH -N 1   # number of nodes
#SBATCH --ntasks-per-node 2 # max number of tasks per node
#SBATCH --mem 64G # memory pool for all cores
#SBATCH --gres=gpu:1  # For any GPU: --gres=gpu:1. For a specific one: --gres=gpu:rtx5000
#SBATCH -t 3-00:00 # time (D-HH:MM)
#SBATCH -o slurm_array.%A-%a.%N.out
#SBATCH -e slurm_array.%A-%a.%N.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user=s.minano@ucl.ac.uk
#SBATCH --array=0-2%3

# NOTE on SBATCH command for array jobs
# with "SBATCH --array=0-n%m" ---> runs n separate jobs, but not more than m at a time.
# the number of array jobs should match the number of input files

# ---------------------
# Source bashrc
# ----------------------
# Otherwise `which python` points to the miniconda module's Python
source ~/.bashrc


# memory
# see https://pytorch.org/docs/stable/notes/cuda.html#environment-variables
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# -----------------------------
# Error settings for bash
# -----------------------------
# see https://wizardzines.com/comics/bash-errors/
set -e  # do not continue after errors
set -u  # throw error if variable is unset
set -o pipefail  # make the pipe fail if any part of it fails

# ---------------------
# Define variables
# ----------------------

# dataset and train config
DATASET_DIR=/ceph/zoo/users/sminano/crabs_bboxes_labels/Sep2023_labelled
TRAIN_CONFIG_FILE=/ceph/scratch/sminano/crabs-exploration/cluster_train_config.yaml

# seeds for each dataset split
LIST_SEEDS=($(echo {42..44}))
SPLIT_SEED=${LIST_SEEDS[${SLURM_ARRAY_TASK_ID}]}

# version of the codebase
GIT_BRANCH=main

# --------------------
# Check inputs
# --------------------
# Check len(list of input data) matches max SLURM_ARRAY_TASK_COUNT
# if not, exit
if [[ $SLURM_ARRAY_TASK_COUNT -ne ${#LIST_SEEDS[@]} ]]; then
    echo "The number of array tasks does not match the number of inputs"
    exit 1
fi

# -----------------------------
# Create virtual environment
# -----------------------------
module load miniconda

# define a environment for the whole array of jobs in the
# temporary directory of the compute node
# (if two jobs share a node, the env is not created again)
ENV_NAME=crabs-dev-$SLURM_ARRAY_JOB_ID
ENV_PREFIX=$TMPDIR/$ENV_NAME

# if environment does not exist: create it
if [ ! -d "$ENV_PREFIX" ]; then
    # create environment
    conda create \
        --prefix $ENV_PREFIX \
        -y \
        python=3.10

    # activate
    conda activate $ENV_PREFIX

    # install crabs package in virtual env
    python -m pip install git+https://github.com/SainsburyWellcomeCentre/crabs-exploration.git@$GIT_BRANCH

else
    # activate environment
    conda activate $ENV_PREFIX
fi


# log pip and python locations
echo $ENV_PREFIX
which python
which pip

# print the version of crabs package (last number is the commit hash)
echo "Git branch: $GIT_BRANCH"
conda list crabs
echo "-----"

# ------------------------------------
# GPU specs
# ------------------------------------
echo "Memory used per GPU before training"
echo $(nvidia-smi --query-gpu=name,memory.total,memory.free,memory.used --format=csv) #noheader
echo "-----"

# -------------------
# Run training script
# -------------------
train-detector  \
 --dataset_dirs $DATASET_DIR \
 --config_file $TRAIN_CONFIG_FILE \
 --accelerator gpu \
 --experiment_name "Sept2023_base_data_augm" \
 --seed_n $SPLIT_SEED \