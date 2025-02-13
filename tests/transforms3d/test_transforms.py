import pytest
import numpy as np
import albumentations as A
import cv2

from tests.conftest import RECTANGULAR_UINT8_IMAGE, SQUARE_UINT8_IMAGE
from tests.utils import get_2d_transforms, get_3d_transforms

@pytest.mark.parametrize(
    ["volume_shape", "min_zyx", "pad_divisor_zyx", "expected_shape"],
    [
        # Test no padding needed
        ((10, 100, 100), (10, 100, 100), None, (10, 100, 100)),

        # Test 2D-like behavior (no z padding)
        ((10, 100, 100), (10, 128, 128), None, (10, 128, 128)),

        # Test padding in all dimensions
        ((10, 100, 100), (16, 128, 128), None, (16, 128, 128)),

        # Test divisibility padding
        ((10, 100, 100), None, (8, 32, 32), (16, 128, 128)),

        # Test mixed min_size and divisibility
        ((10, 100, 100), (16, 128, 128), (8, 32, 32), (16, 128, 128)),
    ]
)
def test_pad_if_needed_3d_shapes(volume_shape, min_zyx, pad_divisor_zyx, expected_shape):
    volume = np.random.randint(0, 256, volume_shape, dtype=np.uint8)
    transform = A.PadIfNeeded3D(
        min_zyx=min_zyx,
        pad_divisor_zyx=pad_divisor_zyx,
        position="center",
        fill=0,
        fill_mask=0
    )
    transformed = transform(volume=volume)
    assert transformed["volume"].shape == expected_shape

@pytest.mark.parametrize("position", ["center", "random"])
def test_pad_if_needed_3d_positions(position):
    volume = np.ones((5, 50, 50), dtype=np.uint8)
    transform = A.PadIfNeeded3D(
        min_zyx=(10, 100, 100),
        position=position,
        fill=0,
        fill_mask=0
    )
    transformed = transform(volume=volume)
    # Check that the original volume is preserved somewhere in the padded volume
    assert np.any(transformed["volume"] == 1)

def test_pad_if_needed_3d_2d_equivalence():
    """Test that PadIfNeeded3D behaves like PadIfNeeded when no z-padding is needed"""
    # Create a volume with multiple identical slices
    slice_2d = np.random.randint(0, 256, (100, 100), dtype=np.uint8)
    volume_3d = np.stack([slice_2d] * 10)

    # Apply 3D padding with no z-axis changes
    transform_3d = A.PadIfNeeded3D(
        min_zyx=(10, 128, 128),
        position="center",
        fill=0,
        fill_mask=0
    )
    transformed_3d = transform_3d(volume=volume_3d)

    # Apply 2D padding to a single slice
    transform_2d = A.PadIfNeeded(
        min_height=128,
        min_width=128,
        position="center",
        border_mode=cv2.BORDER_CONSTANT,
        fill=0,
        fill_mask=0
    )
    transformed_2d = transform_2d(image=slice_2d)

    # Compare each slice of 3D result with 2D result
    for slice_idx in range(10):
        np.testing.assert_array_equal(
            transformed_3d["volume"][slice_idx],
            transformed_2d["image"]
        )

def test_pad_if_needed_3d_fill_values():
    volume = np.zeros((5, 50, 50), dtype=np.uint8)
    mask3d = np.ones((5, 50, 50), dtype=np.uint8)

    transform = A.PadIfNeeded3D(
        min_zyx=(10, 100, 100),
        position="center",
        fill=255,
        fill_mask=128
    )

    transformed = transform(volume=volume, mask3d=mask3d)

    # Check fill values in padded regions
    assert np.all(transformed["volume"][:, :25, :] == 255)  # top padding
    assert np.all(transformed["mask3d"][:, :25, :] == 128)  # top padding in mask


@pytest.mark.parametrize(
    ["augmentation_cls", "params"],
    get_3d_transforms(
        custom_arguments={
            A.PadIfNeeded3D: {"min_zyx": (4, 250, 230), "position": "center", "fill": 0, "fill_mask": 0},
            A.Pad3D: {"padding": 10},
            A.RandomCrop3D: {"size": (2, 30, 30), "pad_if_needed": True},
            A.CenterCrop3D: {"size": (2, 30, 30), "pad_if_needed": True},
        },
        except_augmentations={
        },
    ),
)
def test_augmentations_match_uint8_float32(augmentation_cls, params):
    image_uint8 = RECTANGULAR_UINT8_IMAGE
    image_float32 = image_uint8 / 255.0

    transform = A.Compose([augmentation_cls(p=1, **params)], seed=42)

    volume = np.stack([image_uint8, image_uint8])

    data = {"volume": volume}

    transformed_uint8 = transform(**data)["volume"]

    data["volume"] = np.stack([image_float32, image_float32])

    transform.set_random_seed(42)
    transformed_float32 = transform(**data)["volume"]

    np.testing.assert_array_almost_equal(transformed_uint8 / 255.0, transformed_float32, decimal=2)


@pytest.mark.parametrize(
    ["padding", "expected_shape"],
    [
        # Single int - pad all sides equally
        (2, (14, 14, 14, 1)),  # 10+2+2 = 14 for each dimension

        # 3-tuple - symmetric padding per dimension
        ((1, 2, 3), (12, 14, 16, 1)),  # d+2, h+4, w+6

        # 6-tuple - specific padding per side
        ((1, 2, 3, 2, 1, 4), (13, 15, 15, 1)),  # (d+3, h+3, w+7)

        # Zero padding
        (0, (10, 10, 10, 1)),  # Original shape
    ],
)
def test_pad3d_shapes(padding, expected_shape):
    volume = np.ones((10, 10, 10, 1), dtype=np.float32)
    augmentation = A.Pad3D(padding=padding)
    padded = augmentation(volume=volume)["volume"]
    assert padded.shape == expected_shape


@pytest.mark.parametrize(
    ["fill", "fill_mask"],
    [
        (0, 1),
        (1, 0),
    ],
)
def test_pad3d_fill_values(fill, fill_mask):
    volume = np.ones((3, 3, 3, 1), dtype=np.float32)
    mask3d = np.ones((3, 3, 3, 1), dtype=np.float32)

    augmentation = A.Pad3D(padding=1, fill=fill, fill_mask=fill_mask)
    transformed = augmentation(volume=volume, mask3d=mask3d)

    padded_volume = transformed["volume"]
    padded_mask = transformed["mask3d"]

    # Check fill values in padded regions
    assert np.all(padded_volume[0, :, :] == fill)  # front slice
    assert np.all(padded_mask[0, :, :] == fill_mask)  # front slice of mask


@pytest.mark.parametrize(
    "volume_shape",
    [
        (10, 10, 10),      # 3D
        (10, 10, 10, 1),   # 4D single channel
        (10, 10, 10, 3),   # 4D multi-channel
    ],
)
def test_pad3d_different_shapes(volume_shape):
    volume = np.ones(volume_shape, dtype=np.float32)
    augmentation = A.Pad3D(padding=2)
    padded = augmentation(volume=volume)["volume"]

    expected_shape = tuple(s + 4 for s in volume_shape[:3])  # +4 because padding=2 on each side
    if len(volume_shape) == 4:
        expected_shape += (volume_shape[3],)

    assert padded.shape == expected_shape


def test_pad3d_different_dtypes():
    for dtype in [np.uint8, np.float32]:
        volume = np.ones((5, 5, 5), dtype=dtype)
        augmentation = A.Pad3D(padding=1)
        padded = augmentation(volume=volume)["volume"]
        assert padded.dtype == dtype


def test_pad3d_preservation():
    """Test that the original data is preserved in the non-padded region"""
    volume = np.random.randint(0, 255, (5, 5, 5), dtype=np.uint8)
    augmentation = A.Pad3D(padding=2)
    padded = augmentation(volume=volume)["volume"]

    # Check if the original volume is preserved in the center
    np.testing.assert_array_equal(
        padded[2:-2, 2:-2, 2:-2],
        volume
    )

@pytest.mark.parametrize(
    ["pad3d_padding", "pad2d_padding"],
    [
        # 6-tuple for 3D (z_front, z_back, y_top, y_bottom, x_left, x_right) vs
        # 4-tuple for 2D (y_top, y_bottom, x_left, x_right)
        ((0, 0, 10, 10, 20, 20), (20, 10, 20, 10)),
        # 3-tuple for 3D (d,h,w) vs 2-tuple for 2D (w,h) - symmetric padding
        ((0, 10, 20), (20, 10)),
    ],
    ids=[
        "explicit_padding",
        "symmetric_padding",
    ]
)
def test_pad3d_2d_equivalence(pad3d_padding, pad2d_padding):
    """Test that Pad3D behaves like Pad when no z-padding is applied"""
    # Create a volume with multiple identical slices
    num_slices = 4
    slice_2d = np.random.randint(0, 256, (3, 3), dtype=np.uint8)
    volume_3d = np.stack([slice_2d] * num_slices)  # 10 identical slices

    # Apply 3D padding with no z-axis changes
    transform_3d = A.Pad3D(
        padding=pad3d_padding,
        fill=0,
        fill_mask=0
    )
    transformed_3d = transform_3d(volume=volume_3d)

    # Apply 2D padding to a single slice
    transform_2d = A.Pad(
        padding=pad2d_padding,
        fill=0,
        fill_mask=0
    )
    transformed_2d = transform_2d(image=slice_2d)

    # Compare each slice of 3D result with 2D result
    for slice_idx in range(num_slices):
        np.testing.assert_array_equal(
            transformed_3d["volume"][slice_idx],
            transformed_2d["image"]
        )

    # Also verify that z dimension hasn't changed
    assert transformed_3d["volume"].shape[0] == volume_3d.shape[0]


@pytest.mark.parametrize(
    ["augmentation_cls", "params"],
    get_3d_transforms(
        custom_arguments={
            A.PadIfNeeded3D: {"min_zyx": (300, 200, 400), "pad_divisor_zyx": (10, 10, 10), "position": "center", "fill": 10, "fill_mask": 20},
            A.Pad3D: {"padding": 10},
            A.RandomCrop3D: {"size": (2, 30, 30), "pad_if_needed": True},
            A.CenterCrop3D: {"size": (2, 30, 30), "pad_if_needed": True},
        },
        except_augmentations={
        },
    ),
)
def test_change_volume(volume, mask3d,augmentation_cls, params):
    """Checks whether resulting volume is different from the original one."""
    aug = A.Compose([augmentation_cls(p=1, **params)], seed=0)

    original_volume = volume.copy()
    original_mask3d = mask3d.copy()

    data = {
        "volume": volume,
        "mask3d": mask3d,
    }
    transformed = aug(**data)

    assert not np.array_equal(transformed["volume"], original_volume)
    assert not np.array_equal(transformed["mask3d"], original_mask3d)


@pytest.mark.parametrize(
    ["transform", "input_shape", "expected_shape"],
    [
        # CenterCrop3D tests
        (
            A.CenterCrop3D(size=(4, 60, 60), pad_if_needed=False, fill=0, fill_mask=0),
            (10, 100, 100),
            (4, 60, 60),
        ),
        # RandomCrop3D tests
        (
            A.RandomCrop3D(size=(4, 60, 60), pad_if_needed=False, fill=0, fill_mask=0),
            (10, 100, 100),
            (4, 60, 60),
        ),
    ],
    ids=[
        "center_crop_3d",
        "random_crop_3d",
    ]
)
def test_crop_3d_shapes(transform, input_shape, expected_shape):
    volume = np.random.randint(0, 256, input_shape, dtype=np.uint8)
    transformed = transform(volume=volume)
    assert transformed["volume"].shape == expected_shape


@pytest.mark.parametrize(
    "transform_cls",
    [
        A.CenterCrop3D,
        A.RandomCrop3D,
    ],
    ids=[
        "center_crop",
        "random_crop",
    ]
)
@pytest.mark.parametrize(
    ["input_shape", "target_shape", "description"],
    [
        # Padding needed in all dimensions
        (
            (10, 100, 100),
            (16, 128, 128),
            "pad_all_dims",
        ),
        # Padding needed only in depth
        (
            (5, 100, 100),
            (10, 50, 50),
            "pad_depth_only",
        ),
        # Padding needed only in height
        (
            (10, 40, 100),
            (8, 64, 50),
            "pad_height_only",
        ),
        # Padding needed only in width
        (
            (10, 100, 40),
            (8, 50, 64),
            "pad_width_only",
        ),
        # Padding needed in height and width
        (
            (10, 40, 40),
            (8, 64, 64),
            "pad_height_width",
        ),
        # No padding needed (smaller crop)
        (
            (10, 100, 100),
            (8, 64, 64),
            "no_padding_needed",
        ),
    ],
    ids=lambda x: x[2] if isinstance(x, tuple) else x,
)
def test_crop_3d_padding(transform_cls, input_shape, target_shape, description):
    volume = np.random.randint(0, 256, input_shape, dtype=np.uint8)

    transform = A.Compose([transform_cls(p=1, size=target_shape, pad_if_needed=True, fill=0, fill_mask=0)], seed=0)

    transformed = transform(volume=volume)
    assert transformed["volume"].shape == target_shape


@pytest.mark.parametrize(
    ["transform_cls", "size", "fill", "fill_mask"],
    [
        (A.CenterCrop3D, (4, 60, 60), 0, 1),
        (A.CenterCrop3D, (4, 60, 60), 1, 0),
        (A.RandomCrop3D, (4, 60, 60), 0, 1),
        (A.RandomCrop3D, (4, 60, 60), 1, 0),
    ],
    ids=[
        "center_crop_fill_0_mask_1",
        "center_crop_fill_1_mask_0",
        "random_crop_fill_0_mask_1",
        "random_crop_fill_1_mask_0",
    ]
)
def test_crop_3d_fill_values(transform_cls, size, fill, fill_mask):
    volume = np.ones((3, 50, 50), dtype=np.uint8)
    mask3d = np.zeros((3, 50, 50), dtype=np.uint8)

    transform = A.Compose([transform_cls(p=1, size=size, pad_if_needed=True, fill=fill, fill_mask=fill_mask)], seed=0)

    transformed = transform(volume=volume, mask3d=mask3d)
    padded_volume = transformed["volume"]
    padded_mask = transformed["mask3d"]

    # Verify shapes
    assert padded_volume.shape == size
    assert padded_mask.shape == size

    # Find padded regions by comparing with fill values
    is_padding_volume = padded_volume == fill
    is_padding_mask = padded_mask == fill_mask

    # Check that some padding exists in each dimension that needs it
    if size[0] > volume.shape[0]:
        assert np.any(is_padding_volume[:, 0, 0])  # depth padding exists
        assert np.any(is_padding_mask[:, 0, 0])

    if size[1] > volume.shape[1]:
        assert np.any(is_padding_volume[0, :, 0])  # height padding exists
        assert np.any(is_padding_mask[0, :, 0])

    if size[2] > volume.shape[2]:
        assert np.any(is_padding_volume[0, 0, :])  # width padding exists
        assert np.any(is_padding_mask[0, 0, :])

    # Check that padding values are consistent
    assert np.all(padded_volume[is_padding_volume] == fill)
    assert np.all(padded_mask[is_padding_mask] == fill_mask)


def test_random_crop_3d_reproducibility():
    """Test that RandomCrop3D produces same results with same random seed"""
    volume = np.random.randint(0, 256, (10, 100, 100), dtype=np.uint8)

    transform = A.RandomCrop3D(size=(4, 60, 60))

    # First run
    transform.set_random_seed(42)
    result1 = transform(volume=volume)["volume"]

    # Second run
    transform.set_random_seed(42)
    result2 = transform(volume=volume)["volume"]

    np.testing.assert_array_equal(result1, result2)


@pytest.mark.parametrize(
    "volume_shape",
    [
        (10, 100, 100),      # 3D
        (10, 100, 100, 1),   # 4D single channel
        (10, 100, 100, 3),   # 4D multi-channel
    ],
    ids=[
        "3d_volume",
        "4d_single_channel",
        "4d_multi_channel",
    ]
)
def test_crop_3d_different_shapes(volume_shape):
    volume = np.random.randint(0, 256, volume_shape, dtype=np.uint8)

    for transform_cls in [A.CenterCrop3D, A.RandomCrop3D]:
        transform = transform_cls(size=(4, 60, 60))
        transformed = transform(volume=volume)

        expected_shape = (4, 60, 60)
        if len(volume_shape) == 4:
            expected_shape += (volume_shape[3],)

        assert transformed["volume"].shape == expected_shape


@pytest.mark.parametrize(
    ["augmentation_cls", "params"],
    get_3d_transforms(
        custom_arguments={
            A.PadIfNeeded3D: {"min_zyx": (300, 200, 400), "pad_divisor_zyx": (10, 10, 10), "position": "center", "fill": 10, "fill_mask": 20},
            A.Pad3D: {"padding": 10},
            A.RandomCrop3D: {"size": (2, 30, 30), "pad_if_needed": True},
            A.CenterCrop3D: {"size": (2, 30, 30), "pad_if_needed": True},
        },
        except_augmentations={
        },
    ),
)
def test_return_nonzero(volume, mask3d, augmentation_cls, params):
    """Mistakes in clipping may lead to zero image, testing for that"""

    aug = A.Compose([augmentation_cls(**params, p=1)], seed=42)

    data = {
        "volume": volume,
        "mask3d": mask3d,
    }

    result = aug(**data)

    assert np.max(result["volume"]) > 0
    assert np.max(result["mask3d"]) > 0


def test2d_3d(volume, mask3d):
    transform = A.Compose([A.RandomCrop3D(size=(2, 30, 30), pad_if_needed=True, p=1), A.HorizontalFlip(p=1)])

    transformed = transform(volume=volume, mask3d=mask3d)
    assert np.max(transformed["volume"]) > 0
    assert np.max(transformed["mask3d"]) > 0


@pytest.mark.parametrize(
    ["augmentation_cls", "params"],
    get_2d_transforms(
        custom_arguments={
            A.RandomCrop: {"height": 50, "width": 50},
            A.AtLeastOneBBoxRandomCrop: {"height": 50, "width": 50},
            A.CenterCrop: {"height": 50, "width": 50},
            A.GridElasticDeform: {"num_grid_xy": (10, 10), "magnitude": 10},
            A.Resize: {"height": 100, "width": 100},
        },
        except_augmentations={
            A.RandomSizedBBoxSafeCrop,
            A.PixelDropout,
            A.FDA,
            A.MaskDropout,
            A.CropNonEmptyMaskIfExists,
            A.BBoxSafeRandomCrop,
            A.TextImage,
            A.OverlayElements,
            A.PixelDistributionAdaptation,
            A.HistogramMatching,
            A.TemplateTransform,

        },
    ),
)
def test_image_volume_matching(image,augmentation_cls, params):
    aug = A.Compose([augmentation_cls(**params, p=1)], seed=42)

    volume = np.stack([image.copy()] * 4, axis=0)
    images = np.stack([image.copy()] * 5, axis=0)

    volumes = np.stack([volume.copy()] * 2, axis=0)

    transformed = aug(image=image, volumes=volumes, volume=volume, images=images)

    np.testing.assert_allclose(transformed["image"], transformed["images"][0], atol=4, rtol=1e-1), f"Image shape = {transformed['image'].shape}, Images shape = {transformed['images'].shape}"
    np.testing.assert_allclose(transformed["image"], transformed["volume"][0], atol=4, rtol=1e-1), f"Image shape = {transformed['image'].shape}, Volume shape = {transformed['volume'].shape}"
    np.testing.assert_allclose(transformed["volume"], transformed["volumes"][0], atol=1, rtol=1e-3), f"Volume shape = {transformed['volume'].shape}, Volumes shape = {transformed['volumes'].shape}"
