import argparse
import datetime

import lightning as pl
import torch
import yaml  # type: ignore

from crabs.detection_tracking.datamodules import CrabsDataModule
from crabs.detection_tracking.detection_utils import save_model
from crabs.detection_tracking.models import FasterRCNN


class DectectorTrain:
    """Training class for detector algorithm

    Parameters
    ----------
    args: argparse.Namespace
        An object containing the parsed command-line arguments.

    Attributes
    ----------
    config_file : str
        Path to the directory containing configuration file.
    main_dirs : List[str]
        List of paths to the main directories of the datasets.
    annotation_files : List[str]
        List of filenames for the COCO annotations.
    model_name : str
        The model use to train the detector.
    """

    def __init__(self, args):
        self.config_file = args.config_file
        self.images_dirs = args.images_dirs  # list of paths
        self.annotation_files = args.annotation_files  # list of paths
        self.accelerator = args.accelerator
        self.seed_n = args.seed_n
        self.load_config_yaml()

    def load_config_yaml(self):
        with open(self.config_file, "r") as f:
            self.config = yaml.safe_load(f)

    def train_model(self):
        # Create data module
        data_module = CrabsDataModule(
            self.images_dirs,  # list of paths
            self.annotation_files,  # list of paths
            self.config,
            self.seed_n,
        )

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_name = f"run_{timestamp}"

        # Initialise MLflow logger
        mlf_logger = pl.pytorch.loggers.MLFlowLogger(
            run_name=run_name,
            experiment_name=args.experiment_name,
            tracking_uri="file:./ml-runs",
        )

        mlf_logger.log_hyperparams(self.config)

        lightning_model = FasterRCNN(self.config)

        trainer = pl.Trainer(
            max_epochs=self.config["num_epochs"],
            accelerator=self.accelerator,
            logger=mlf_logger,
        )

        # Run training
        trainer.fit(lightning_model, data_module)

        # Save model if required
        if self.config["save"]:
            save_model(lightning_model)


def main(args) -> None:
    """
    Main function to orchestrate the training process.

    Parameters
    ----------
    args: argparse.Namespace
        An object containing the parsed command-line arguments.

    Returns
    ----------
    None
    """
    trainer = DectectorTrain(args)
    trainer.train_model()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config_file",
        type=str,
        default="crabs/detection_tracking/config/faster_rcnn.yaml",
        help="location of YAML config to control training",
    )
    parser.add_argument(
        "--images_dirs",
        nargs="+",
        required=True,
        help="list of paths to images directories",
    )
    parser.add_argument(
        "--annotation_files",
        nargs="+",
        required=True,
        help="list of paths to annotation files",
    )
    parser.add_argument(
        "--accelerator",
        type=str,
        default="gpu",
        help="accelerator for pytorch lightning",
    )
    parser.add_argument(
        "--experiment_name",
        type=str,
        default="Sept2023",
        help="the name for the experiment in MLflow, under which the current run will be logged. For example, the name of the dataset could be used, to group runs using the same data.",
    )
    parser.add_argument(
        "--seed_n",
        type=int,
        default=42,
        help="seed for dataset splits",
    )
    args = parser.parse_args()
    torch.set_float32_matmul_precision("medium")
    main(args)
