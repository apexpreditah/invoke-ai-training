import typing

from torch.utils.data import ConcatDataset, DataLoader
from transformers import CLIPTokenizer

from invoke_training.training.config.data_config import ImageDirDatasetConfig
from invoke_training.training.shared.data.data_loaders.dreambooth_samplers import (
    InterleavedSampler,
    SequentialRangeSampler,
    ShuffledRangeSampler,
)
from invoke_training.training.shared.data.datasets.image_dir_dataset import (
    ImageDirDataset,
)
from invoke_training.training.shared.data.datasets.transform_dataset import (
    TransformDataset,
)
from invoke_training.training.shared.data.transforms.constant_field_transform import (
    ConstantFieldTransform,
)
from invoke_training.training.shared.data.transforms.sd_image_transform import (
    SDImageTransform,
)
from invoke_training.training.shared.data.transforms.sd_tokenize_transform import (
    SDTokenizeTransform,
)


def build_dreambooth_sd_dataloader(
    instance_prompt: str,
    instance_dataset_config: ImageDirDatasetConfig,
    class_prompt: typing.Optional[str],
    class_data_dir: typing.Optional[str],
    tokenizer: typing.Optional[CLIPTokenizer],
    batch_size: int,
    shuffle: bool = True,
) -> DataLoader:
    """Construct a DataLoader for a DreamBooth dataset for Stable Diffusion v1/v2.."""

    # 1. Prepare instance dataset
    instance_dataset = ImageDirDataset(instance_dataset_config.dataset_dir)
    instance_dataset = TransformDataset(
        instance_dataset,
        [ConstantFieldTransform("caption", instance_prompt), ConstantFieldTransform("loss_weight", 1.0)],
    )
    datasets = [instance_dataset]

    # 2. Prepare class dataset.
    class_dataset = None
    if class_data_dir is not None:
        class_dataset = ImageDirDataset(class_data_dir)
        class_dataset = TransformDataset(
            class_dataset,
            [ConstantFieldTransform("caption", class_prompt), ConstantFieldTransform("loss_weight", 1.0)],
        )
        datasets.append(class_dataset)

    # 3. Merge instance dataset and class dataset.
    merged_dataset = ConcatDataset(datasets)
    all_transforms = [
        SDImageTransform(
            resolution=instance_dataset_config.image_transforms.resolution,
            center_crop=instance_dataset_config.image_transforms.center_crop,
            random_flip=instance_dataset_config.image_transforms.random_flip,
        ),
        SDTokenizeTransform(tokenizer),
    ]
    merged_dataset = TransformDataset(merged_dataset, all_transforms)

    # 4. Prepare instance dataset sampler. Note that the instance_dataset comes first in the merged_dataset.
    samplers = []
    if shuffle:
        samplers.append(SequentialRangeSampler(0, len(instance_dataset)))
    else:
        samplers.append(ShuffledRangeSampler(0, len(instance_dataset)))

    # 5. Prepare class dataset sampler. Note that the class_dataset comes first in the merged_dataset.
    if class_dataset is not None:
        if shuffle:
            samplers.append(SequentialRangeSampler(len(instance_dataset), len(instance_dataset) + len(class_dataset)))
        else:
            samplers.append(ShuffledRangeSampler(len(instance_dataset), len(instance_dataset) + len(class_dataset)))

    # 6. Interleave instance and class samplers.
    interleaved_sampler = InterleavedSampler(samplers)

    return DataLoader(
        merged_dataset,
        sampler=interleaved_sampler,
        batch_size=batch_size,
        num_workers=instance_dataset_config.dataloader_num_workers,
    )
