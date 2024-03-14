# https://pytorch.org/tutorials/beginner/basics/data_tutorial.html#creating-a-custom-dataset-for-your-files
# The PyTorch Dataset represents a map from keys to data samples.
# dataloader: The PyTorch DataLoader represents a Python iterable over a DataSet.

import matplotlib.pyplot as plt
import torch
from torchvision import tv_tensors
from torchvision.datasets import CocoDetection, wrap_dataset_for_transforms_v2
from torchvision.transforms.v2 import functional as F
from torchvision.utils import draw_bounding_boxes, draw_segmentation_masks


class CrabsCocoDetection(torch.utils.data.ConcatDataset):
    def __init__(self, list_img_dirs, list_annotation_files, transforms=None):
        """
        CocoDetection dataset wrapped for transforms_v2.

        Example:
        > dataset = CrabsCocoDetection(IMAGES_PATH, ANNOTATIONS_PATH)

        > sample = dataset[0]
        > img, annotations = sample
        > print(type(annotations))  # this is a dictionary

        Should be equivalent to the dataset obtain with:
        > dataset = wrap_dataset_for_transforms_v2(CocoDetection(IMAGES_PATH, ANNOTATIONS_PATH))
        """

        # Create list of transformed-COCO datasets
        list_datasets = []
        for img_dir, annotation_file in zip(
            list_img_dirs, list_annotation_files
        ):
            dataset_coco = CocoDetection(
                img_dir,
                annotation_file,
                transforms=transforms,
                # exclude_files_w_regex------------------
            )
            dataset_transformed = wrap_dataset_for_transforms_v2(dataset_coco)
            list_datasets.append(dataset_transformed)

        # Concatenate datasets
        full_dataset = torch.utils.data.ConcatDataset(list_datasets)

        # Update class
        self.__class__ = full_dataset.__class__
        self.__dict__ = full_dataset.__dict__


def plot_sample(imgs, row_title=None, **imshow_kwargs):
    """
    Plot a sample from the dataset.

    From https://github.com/pytorch/vision/blob/main/gallery/transforms/helpers.py
    """
    if not isinstance(imgs[0], list):
        # Make a 2d grid even if there's just 1 row
        imgs = [imgs]

    num_rows = len(imgs)
    num_cols = len(imgs[0])
    _, axs = plt.subplots(nrows=num_rows, ncols=num_cols, squeeze=False)
    for row_idx, row in enumerate(imgs):
        for col_idx, img in enumerate(row):
            boxes = None
            masks = None
            if isinstance(img, tuple):
                img, target = img
                if isinstance(target, dict):
                    boxes = target.get("boxes")
                    masks = target.get("masks")
                elif isinstance(target, tv_tensors.BoundingBoxes):
                    boxes = target
                else:
                    raise ValueError(f"Unexpected target type: {type(target)}")
            img = F.to_image(img)
            if img.dtype.is_floating_point and img.min() < 0:
                # Poor man's re-normalization for the colors to be OK-ish. This
                # is useful for images coming out of Normalize()
                img -= img.min()
                img /= img.max()

            img = F.to_dtype(img, torch.uint8, scale=True)
            if boxes is not None:
                img = draw_bounding_boxes(img, boxes, colors="yellow", width=3)
            if masks is not None:
                img = draw_segmentation_masks(
                    img,
                    masks.to(torch.bool),
                    colors=["green"] * masks.shape[0],
                    alpha=0.65,
                )

            ax = axs[row_idx, col_idx]
            ax.imshow(img.permute(1, 2, 0).numpy(), **imshow_kwargs)
            ax.set(xticklabels=[], yticklabels=[], xticks=[], yticks=[])

    if row_title is not None:
        for row_idx in range(num_rows):
            axs[row_idx, 0].set(ylabel=row_title[row_idx])

    plt.tight_layout()