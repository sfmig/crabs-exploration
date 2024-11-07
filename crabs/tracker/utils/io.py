"""Utility functions for handling input and output operations."""

import csv
import logging
from pathlib import Path

import cv2
import numpy as np

from crabs.detector.utils.visualization import draw_bbox


def get_video_parameters(video: cv2.VideoCapture) -> dict:
    """Get total number of frames, frame width and height, and fps of video."""
    video_parameters = {}
    video_parameters["total_frames"] = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    video_parameters["frame_width"] = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_parameters["frame_height"] = int(
        video.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )
    video_parameters["fps"] = video.get(cv2.CAP_PROP_FPS)
    return video_parameters


def write_tracked_detections_to_csv(
    csv_file_path: str,
    tracked_bboxes_dict: dict,
    frame_name_regexp: str = "frame_{frame_idx:08d}.png",
    all_frames_size: int = 8888,
):
    """Write tracked detections to a csv file."""
    # Initialise csv file
    csv_file = open(  # noqa: SIM115
        csv_file_path,
        "w",
    )
    csv_writer = csv.writer(csv_file)

    # write header following VIA convention
    # https://www.robots.ox.ac.uk/~vgg/software/via/docs/face_track_annotation.html
    csv_writer.writerow(
        (
            "filename",
            "file_size",
            "file_attributes",
            "region_count",
            "region_id",
            "region_shape_attributes",
            "region_attributes",
        )
    )

    # write detections
    # loop thru frames
    for frame_idx in tracked_bboxes_dict:
        # loop thru all boxes in frame
        for bbox, pred_score in zip(
            tracked_bboxes_dict[frame_idx]["bboxes_tracked"],
            tracked_bboxes_dict[frame_idx]["bboxes_scores"],
        ):
            # extract shape
            xmin, ymin, xmax, ymax, id = bbox
            width_box = int(xmax - xmin)
            height_box = int(ymax - ymin)

            # Add to csv
            csv_writer.writerow(
                (
                    frame_name_regexp.format(
                        frame_idx=frame_idx
                    ),  # f"frame_{frame_idx:08d}.png",  # frame index!
                    all_frames_size,  # frame size
                    '{{"clip":{}}}'.format("123"),
                    1,
                    0,
                    f'{{"name":"rect","x":{xmin},"y":{ymin},"width":{width_box},"height":{height_box}}}',
                    f'{{"track":"{int(id)}", "confidence":"{pred_score}"}}',
                )
            )


def write_frame_to_output_video(
    frame: np.ndarray,
    tracked_bboxes_one_frame: np.ndarray,
    output_video_object: cv2.VideoWriter,
) -> None:
    """Write frame with tracked bounding boxes to output video."""
    frame_copy = frame.copy()  # why copy?
    for bbox in tracked_bboxes_one_frame:
        xmin, ymin, xmax, ymax, id = bbox

        draw_bbox(
            frame_copy,
            (xmin, ymin),
            (xmax, ymax),
            (0, 0, 255),
            f"id : {int(id)}",
        )
    output_video_object.write(frame_copy)


def write_frame_as_image(frame, frame_path):
    """Write frame as image without detections."""
    img_saved = cv2.imwrite(
        frame_path,
        frame,
    )
    if not img_saved:
        logging.error(
            f"Error saving {frame_path}."  # f"frame_{frame_idx:08d}.png"
        )


def parse_video_frame_reading_error_and_log(frame_idx, total_frames):
    """Parse error message for reading a video frame."""
    if frame_idx == total_frames:
        logging.info(f"All {total_frames} frames processed")
    else:
        logging.info(
            f"Error reading frame index " f"{frame_idx}/{total_frames}."
        )


def generate_tracked_video(
    input_video_object, output_video_object, tracked_bboxes
):
    """Generate tracked video."""
    # Loop over frames
    frame_idx = 0
    while input_video_object.isOpened():
        # Read frame
        ret, frame = input_video_object.read()
        if not ret:
            parse_video_frame_reading_error_and_log(
                frame_idx,
                int(input_video_object.get(cv2.CAP_PROP_FRAME_COUNT)),
            )
            break

        # Write frame to output video
        write_frame_to_output_video(
            frame,
            tracked_bboxes[frame_idx]["bboxes_tracked"],
            output_video_object,
        )

        frame_idx += 1

    # Release video objects
    input_video_object.release()
    output_video_object.release()
    cv2.destroyAllWindows()

    return frame_idx


def write_all_video_frames_as_images(
    input_video_object: cv2.VideoCapture,
    frames_subdir: Path,
    frame_name_format_str: str = "frame_{frame_idx:08d}.png",
):
    """Save frames of input video as image files.

    Parameters
    ----------
    input_video_object : cv2.VideoCapture
        The input video object.
    frames_subdir : Path
        The directory to save frames.
    frame_name_format_str : str
        The format to follow for the frame filenames.
        E.g. "frame_{frame_idx:08d}.png"

    """
    # Loop over frames
    frame_idx = 0
    while input_video_object.isOpened():
        # Read frame
        ret, frame = input_video_object.read()
        if not ret:
            parse_video_frame_reading_error_and_log(
                frame_idx,
                int(input_video_object.get(cv2.CAP_PROP_FRAME_COUNT)),
            )
            break

        # Write frame to file
        frame_path = str(
            frames_subdir / frame_name_format_str.format(frame_idx=frame_idx)
        )
        write_frame_as_image(frame, frame_path)
