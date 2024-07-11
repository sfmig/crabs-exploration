from pathlib import Path

import numpy as np
import pytest

from crabs.tracker.evaluate_tracker import TrackerEvaluate


@pytest.fixture
def evaluation():
    test_csv_file = Path(__file__).parents[1] / "data" / "gt_test.csv"
    return TrackerEvaluate(test_csv_file, iou_threshold=0.1)


@pytest.mark.parametrize(
    "prev_frame_id_map, current_frame_id_map, expected_output",
    [
        (None, {1: 11, 2: 12, 3: 13, 4: 14}, 0),  # no previous frame
        # ----- a crab (GT=3) that continues to exist ---------
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: 13, 4: 14},
            0,
        ),  # correct
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: np.nan, 4: 14},
            0,
        ),  # crab is missed detection in current frame
        (
            {1: 11, 2: 12, 3: np.nan, 4: 14},
            {1: 11, 2: 12, 3: 13, 4: 14},
            0,
        ),  # crab is missed detection in previous frame
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: 15, 4: 14},
            1,
        ),  # crab is re-IDed in current frame
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: 14},
            1,
        ),  # crab swaps ID with a disappearing crab
        (
            {1: 11, 2: 12, 3: 13},
            {1: 11, 2: 12, 4: 13},
            1,
        ),  # disappear crab swaps ID with an appearing crab
        (
            {1: 11, 2: 12, 3: 13},
            {1: 11, 2: 12, 3: 99, 4: 13},
            2,
        ),  # crab swaps ID with an appearing crab
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: 14, 4: 13},
            2,
        ),  # crab swaps ID with another crab that continues to exist
        # ----- a crab (GT=4) disappears ---------
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: 13},
            0,
        ),  # correct
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: 14},
            1,
        ),  # crab disappears and another pre-existing one takes its ID
        (
            {1: 11, 2: 12, 3: 13, 4: 14},
            {1: 11, 2: 12, 3: 13, 5: 14},
            1,
        ),  # crab disappears and an appearing one takes its ID
        (
            {1: 11, 2: 12, 3: 13, 4: np.nan},
            {1: 11, 2: 12, 3: 13},
            0,
        ),  # crab disappears but was missed detection in frame f-1
        (
            {1: 11, 2: 12, 3: 13, 4: np.nan},
            {1: 11, 2: 12, 3: 13, 5: np.nan},
            0,
        ),  # crab disappears but was missed detection in frame f-1, with a new missed crab in frame f
        (
            {1: 11, 2: 12, 3: 13, 4: np.nan},
            {1: 11, 2: 12, 3: np.nan},
            0,
        ),  # crab disappears but was missed detection in frame f-1, and existing crab was missed in frame f
        # ----- a crab (GT=4) appears ---------
        (
            {1: 11, 2: 12, 3: 13},
            {1: 11, 2: 12, 3: 13, 4: 14},
            0,
        ),  # correct
        (
            {1: 11, 2: 12, 3: 14},
            {1: 11, 2: 12, 3: 13, 4: 14},
            2,
        ),  # crab that appears gets ID of a pre-existing crab
        (
            {1: 11, 2: 12, 3: 13},
            {1: 11, 2: 12, 4: 13},
            1,
        ),  # crab that appears gets ID of a crab that disappears
        (
            {1: 11, 2: 12, 3: 13},
            {1: 11, 2: 12, 3: 13, 4: np.nan},
            0,
        ),  # missed detection in current frame
        (
            {1: 11, 2: 12, 3: 13, 5: np.nan},
            {1: 11, 2: 12, 3: 13, 4: np.nan},
            0,
        ),  # crab that appears is missed detection in current frame, and another missed detection in previous frame disappears
        (
            {1: 11, 2: 12, 3: np.nan},
            {1: 11, 2: 12, 3: 13, 4: np.nan},
            0,
        ),  # crab that appears is missed detection in current frame, and a pre-existing crab is missed detection in previous frame
    ],
)
def test_count_identity_switches(
    evaluation, prev_frame_id_map, current_frame_id_map, expected_output
):
    assert (
        evaluation.count_identity_switches(
            prev_frame_id_map, current_frame_id_map
        )
        == expected_output
    )


@pytest.mark.parametrize(
    "gt_data, pred_data, prev_frame_id_map, expected_mota",
    [
        # perfect tracking
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 3]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([11, 12, 13]),
            },
            {1: 11, 2: 12, 3: 13},
            1.0,
        ),
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 3]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([11, 12, 13]),
            },
            {1: 11, 12: 2, 3: np.nan},
            1.0,
        ),
        # ID switch
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 3]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([11, 12, 14]),
            },
            {1: 11, 2: 12, 3: 13},
            2 / 3,
        ),
        # missed detection
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 4]),
            },
            {
                "bbox": np.array(
                    [[10.0, 10.0, 20.0, 20.0], [30.0, 30.0, 40.0, 40.0]]
                ),
                "id": np.array([11, 12]),
            },
            {1: 11, 2: 12, 3: 13},
            2 / 3,
        ),
        # false positive
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 3]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                        [70.0, 70.0, 80.0, 80.0],
                    ]
                ),
                "id": np.array([11, 12, 13, 14]),
            },
            {1: 11, 2: 12, 3: 13},
            2 / 3,
        ),
        # low IOU and ID switch
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 3]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 30.0, 30.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([11, 12, 14]),
            },
            {1: 11, 2: 12, 3: 13},
            0,
        ),
        # low IOU and ID switch on same box
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 3]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 30.0, 30.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([11, 14, 13]),
            },
            {1: 11, 2: 12, 3: 13},
            1 / 3,
        ),
        # current tracked id = prev tracked id, but prev_gt_id != current gt id
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 4]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([11, 12, 13]),
            },
            {1: 11, 2: 12, 3: 13},
            2 / 3,
        ),
        # ID swapped
        (
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([1, 2, 3]),
            },
            {
                "bbox": np.array(
                    [
                        [10.0, 10.0, 20.0, 20.0],
                        [30.0, 30.0, 40.0, 40.0],
                        [50.0, 50.0, 60.0, 60.0],
                    ]
                ),
                "id": np.array([11, 13, 12]),
            },
            {1: 11, 2: 12, 3: 13},
            1 / 3,
        ),
    ],
)
def test_evaluate_mota(
    gt_data,
    pred_data,
    prev_frame_id_map,
    expected_mota,
    evaluation,
):
    mota, _ = evaluation.evaluate_mota(
        gt_data,
        pred_data,
        0.1,
        prev_frame_id_map,
    )
    assert mota == pytest.approx(expected_mota)
