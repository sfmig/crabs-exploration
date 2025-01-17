"""Train FasterRCNN model for object detection."""

import argparse
import logging
import os
import sys
from pathlib import Path

import lightning
import optuna
import torch
import yaml  # type: ignore
from lightning.pytorch.callbacks import ModelCheckpoint

from crabs.detector.datamodules import CrabsDataModule
from crabs.detector.models import FasterRCNN
from crabs.detector.utils.detection import (
    log_dataset_metadata_as_info,
    log_mlflow_metadata_as_info,
    prep_annotation_files,
    prep_img_directories,
    set_mlflow_run_name,
    setup_mlflow_logger,
    slurm_logs_as_artifacts,
)
from crabs.detector.utils.hpo import compute_optimal_hyperparameters
from crabs.detector.utils.train import (
    get_checkpoint_type,
    log_data_augm_as_artifacts,
)

DEFAULT_DETECTOR_CONFIG = str(
    Path(__file__).parent / "config" / "faster_rcnn.yaml"
)


class DetectorTrain:
    """Training class for detector algorithm.

    Parameters
    ----------
    args: argparse.Namespace
        An object containing the parsed command-line arguments.

    """

    def __init__(self, args: argparse.Namespace):
        """Initialise the training class with the given arguments."""
        # inputs
        self.args = args
        self.config_file = args.config_file
        self.load_config_yaml()

        # dataset
        self.images_dirs = prep_img_directories(args.dataset_dirs)
        self.annotation_files = prep_annotation_files(
            args.annotation_files, args.dataset_dirs
        )
        self.seed_n = args.seed_n

        # Hardware
        self.accelerator = args.accelerator

        # MLflow
        self.experiment_name = args.experiment_name
        self.run_name = set_mlflow_run_name()
        self.mlflow_folder = args.mlflow_folder

        # Debugging
        self.fast_dev_run = args.fast_dev_run
        self.limit_train_batches = args.limit_train_batches

        # Restart from checkpoint
        self.checkpoint_path = args.checkpoint_path

        # Log dataset information to screen
        log_dataset_metadata_as_info(self)

        # Log MLflow information to screen
        log_mlflow_metadata_as_info(self)

    def load_config_yaml(self):
        """Load yaml file that contains config parameters."""
        with open(self.config_file) as f:
            self.config = yaml.safe_load(f)

    def setup_trainer(self):
        """Set up trainer with logging and checkpointing."""
        # Setup logger with checkpointing
        mlf_logger = setup_mlflow_logger(
            experiment_name=self.experiment_name,
            run_name=self.run_name,
            mlflow_folder=self.mlflow_folder,
            cli_args=self.args,
            ckpt_config=self.config.get("checkpoint_saving", {}),
            # pass the checkpointing config if defined
        )

        # Add dataset section to MLflow hyperparameters
        mlf_logger.log_hyperparams(
            {
                "dataset/images_dir": self.images_dirs,
                "dataset/annotation_files": self.annotation_files,
                "dataset/seed": self.seed_n,
            }
        )

        # Define checkpointing callback for trainer
        config_ckpt = self.config.get("checkpoint_saving")
        if config_ckpt:
            checkpoint_callback = ModelCheckpoint(
                filename="checkpoint-{epoch}",
                every_n_epochs=config_ckpt["every_n_epochs"],
                save_top_k=config_ckpt["keep_last_n_ckpts"],
                monitor="epoch",
                # monitor the metric "epoch" for selecting which checkpoints
                # to save
                mode="max",  # get the max of the monitored metric
                save_last=config_ckpt["save_last"],
                save_weights_only=config_ckpt["save_weights_only"],
            )
            enable_checkpointing = True
        else:
            checkpoint_callback = None
            enable_checkpointing = False

        # Return trainer linked to callbacks and logger
        return lightning.Trainer(
            max_epochs=self.config["n_epochs"],
            accelerator=self.accelerator,
            logger=mlf_logger,
            enable_checkpointing=enable_checkpointing,
            callbacks=checkpoint_callback,
            fast_dev_run=self.fast_dev_run,
            limit_train_batches=self.limit_train_batches,
        )

    def optuna_objective_fn(self, trial: optuna.Trial) -> float:
        """Objective function for Optuna.

        When used with Optuna, it will maximise precision and recall on the
        validation set.

        Parameters
        ----------
        trial : optuna.Trial
            The trial to optimise.

        Returns
        -------
        float
            The value to maximise.

        """
        # Sample hyperparameters from the search space for this trial
        optuna_config = self.config["optuna"]

        if "learning_rate" in optuna_config:
            self.config["learning_rate"] = trial.suggest_float(
                "learning_rate",
                float(optuna_config["learning_rate"][0]),
                float(optuna_config["learning_rate"][1]),
                log=True,
            )

        if "n_epochs" in optuna_config:
            self.config["n_epochs"] = trial.suggest_int(
                "n_epochs",
                int(optuna_config["n_epochs"][0]),
                int(optuna_config["n_epochs"][1]),
            )

        # Run training
        trainer = self.core_training()

        # Return metric to maximise
        val_precision = trainer.callback_metrics["val_precision_optuna"].item()
        val_recall = trainer.callback_metrics["val_recall_optuna"].item()
        return (val_precision + val_recall) / 2

    def core_training(self) -> lightning.Trainer:
        """Create data module and model and run training.

        Returns
        -------
        lightning.Trainer
            The trainer object used for training.

        """
        # Create data module
        data_module = CrabsDataModule(
            list_img_dirs=self.images_dirs,
            list_annotation_files=self.annotation_files,
            split_seed=self.seed_n,
            config=self.config,
            no_data_augmentation=self.args.no_data_augmentation,
        )

        # Get model
        # (from a previous checkpoint if required)
        if not self.checkpoint_path:
            lightning_model = FasterRCNN(
                self.config, optuna_log=self.args.optuna
            )
            checkpoint_type = None
        else:
            checkpoint_type = get_checkpoint_type(self.checkpoint_path)
            if checkpoint_type == "weights":
                lightning_model = FasterRCNN.load_from_checkpoint(
                    self.checkpoint_path,
                    config=self.config,
                    # overwrite hparams from ckpt with config
                    optuna_log=self.args.optuna,
                )
                # a 'weights' checkpoint is saved with `save_weights_only=True`

        # Get trainer
        trainer = self.setup_trainer()
        if self.args.log_data_augmentation:
            log_data_augm_as_artifacts(trainer.logger, data_module)

        # Run training
        trainer.fit(
            lightning_model,
            data_module,
            ckpt_path=(
                self.checkpoint_path if checkpoint_type == "full" else None
            ),
            # a 'full' checkpoint is one saved with `save_weights_only=False`
            # (automatically restores model, epoch, step, LR schedulers, etc.)
            # see
            # https://lightning.ai/docs/pytorch/stable/common/checkpointing_basic.html#save-hyperparameters
        )

        return trainer

    def train_model(self):
        """Train detector."""
        # Run hyperparameter sweep with Optuna if required
        if self.args.optuna:
            # Optimize hyperparameters in config
            # to maximise validation precision and recall
            best_hyperparameters = compute_optimal_hyperparameters(
                self.optuna_objective_fn,
                config_optuna=self.config["optuna"],
            )

            # Update the config with the best hyperparameters
            self.config.update(best_hyperparameters)

        # Run training
        trainer = self.core_training()

        # if this is a slurm job: add slurm logs as artifacts
        slurm_job_id = os.environ.get("SLURM_JOB_ID")
        slurm_job_name = os.environ.get("SLURM_JOB_NAME")
        if slurm_job_id and (slurm_job_name != "bash"):
            slurm_logs_as_artifacts(trainer.logger, slurm_job_id)


def main(args) -> None:
    """Run detector training.

    Parameters
    ----------
    args: argparse.Namespace
        An object containing the parsed command-line arguments.

    Returns
    -------
    None

    """
    trainer = DetectorTrain(args)
    trainer.train_model()


def train_parse_args(args):
    """Parse command-line arguments for training."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset_dirs",
        nargs="+",
        required=True,
        help="list of dataset directories",
    )
    parser.add_argument(
        "--annotation_files",
        nargs="+",
        default=[],
        help=(
            "list of paths to annotation files. The full path or the filename "
            "can be provided. "
            "If only filename is provided, it is assumed to be under "
            "dataset/annotations."
        ),
    )
    parser.add_argument(
        "--seed_n",
        type=int,
        default=42,
        help="Seed for dataset splits. Default: 42",
    )
    parser.add_argument(
        "--config_file",
        type=str,
        default=DEFAULT_DETECTOR_CONFIG,
        help=(
            "Location of YAML config to control training. "
            "Default: "
            "crabs-exploration/crabs/detection_tracking/config/faster_rcnn.yaml"
        ),
    )
    parser.add_argument(
        "--checkpoint_path",
        type=str,
        default=None,
        help=("Path to checkpoint to resume training. " "Default: None."),
    )
    parser.add_argument(
        "--accelerator",
        type=str,
        default="gpu",
        help=(
            "Accelerator for Pytorch Lightning. "
            "Valid inputs are: cpu, gpu, tpu, ipu, auto, mps. Default: gpu. "
            "See https://lightning.ai/docs/pytorch/stable/common/trainer.html#accelerator "  # noqa: E501
            "and https://lightning.ai/docs/pytorch/stable/accelerators/mps_basic.html#run-on-apple-silicon-gpus"  # noqa: E501
        ),
    )
    parser.add_argument(
        "--experiment_name",
        type=str,
        default="Sept2023",
        help=(
            "Name of the experiment in MLflow, under which "
            "the current run will be logged. "
            "For example, the name of the dataset could be used, "
            "to group runs using the same data. "
            "Default: Sep2023"
        ),
    )
    parser.add_argument(
        "--mlflow_folder",
        type=str,
        default="./ml-runs",
        help=(
            "Path to MLflow directory where to log the training data. "
            "Default: 'ml-runs' directory under the current working directory."
        ),
    )
    parser.add_argument(
        "--no_data_augmentation",
        action="store_true",
        help=(
            "Ignore the data augmentation transforms "
            "defined in the config file"
        ),
    )
    parser.add_argument(
        "--log_data_augmentation",
        action="store_true",
        help=("Log data augmentation transforms to " "MLflow as artifacts"),
    )
    parser.add_argument(
        "--optuna",
        action="store_true",
        help=(
            "Run a hyperparameter optimisation using Optuna prior to training "
            "the model"
        ),
    )
    parser.add_argument(
        "--fast_dev_run",
        action="store_true",
        help="Debugging option to run training for one batch and one epoch",
    )
    parser.add_argument(
        "--limit_train_batches",
        type=float,
        default=1.0,
        help=(
            "Debugging option to run training on a fraction of the "
            "training set. "
            "Default: 1.0 (the full training set)"
        ),
    )
    return parser.parse_args(args)


def app_wrapper():
    """Wrap function to run the training."""
    logging.getLogger().setLevel(logging.INFO)

    torch.set_float32_matmul_precision("medium")

    train_args = train_parse_args(sys.argv[1:])
    main(train_args)


if __name__ == "__main__":
    app_wrapper()
