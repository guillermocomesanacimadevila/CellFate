# 04_examine_mistaken_predictions.py
import sys
import os
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path
import torch
import torch.nn as nn
import torch.nn.functional as F
import tarrow
from torch.utils.data import DataLoader
from datetime import datetime
import logging
from typing import Sequence

# Dynamic TAP path (like in earlier scripts)
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "TAP" / "tarrow"))

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class BasicBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride=1):
        super(BasicBlock, self).__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1)
        self.bn2 = nn.BatchNorm2d(out_channels)

        # If in_channels != out_channels or stride != 1, use a shortcut projection
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride),
                nn.BatchNorm2d(out_channels)
            )
        else:
            self.shortcut = nn.Identity()  # Identity function

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        out = F.relu(out)
        return out

class SimpleResNet(nn.Module):
    def __init__(self, input_shape, num_cls):
        super(SimpleResNet, self).__init__()

        # Unpacking input shape
        batch_size, time_step, channel, height, width = input_shape

        # Initial conv layer takes 32 channels as input
        self.conv1 = nn.Conv2d(channel, 64, kernel_size=3, stride=1, padding=1)
        self.bn1 = nn.BatchNorm2d(64)

        # One ResNet block, using 64 channels for both input and output to ensure identity connection
        self.block = BasicBlock(64, 64, stride=1)  # No downsampling, identity connection ensured

        # Calculate the flattened size for the FC layer
        # The output after block is [batch*time, 64, height, width]
        self.flattened_size = 64 * height * width  # Correct: 64 not 32

        # Fully connected layer for classification
        self.fc = nn.Linear(self.flattened_size, num_cls)

    def forward(self, x):
        # Merge the time_step into the batch dimension to handle 2D convolutions
        batch_size, time_step, channel, height, width = x.shape
        x = x.view(batch_size * time_step, channel, height, width)

        # Apply initial convolution and ResNet block
        x = F.relu(self.bn1(self.conv1(x)))
        x = self.block(x)

        # Reshape for FC layer
        x = x.view(batch_size, time_step, -1)
        x = x.mean(dim=1)  # Temporal mean pooling
        # print(f"Shape after mean pooling: {x.shape}")

        # Classification
        x = self.fc(x)
        return x

# class BasicBlock(nn.Module):
#     def __init__(self, in_channels, out_channels, stride=1):
#         super(BasicBlock, self).__init__()
#         self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1)
#         self.bn1 = nn.BatchNorm2d(out_channels)
#         self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1)
#         self.bn2 = nn.BatchNorm2d(out_channels)
#
#         # If in_channels != out_channels or stride != 1, use a shortcut projection
#         if stride != 1 or in_channels != out_channels:
#             self.shortcut = nn.Sequential(
#                 nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride),
#                 nn.BatchNorm2d(out_channels)
#             )
#         else:
#             self.shortcut = nn.Identity()  # Identity function
#
#     def forward(self, x):
#         out = F.relu(self.bn1(self.conv1(x)))
#         out = self.bn2(self.conv2(out))
#         out += self.shortcut(x)
#         out = F.relu(out)
#         return out

# class ClsHead(nn.Module):
#     def __init__(self, input_shape, num_cls):
#         super(ClsHead, self).__init__()
#
#         # Unpacking input shape
#         batch_size, time_step, channel, height, width = input_shape
#
#         # Initial conv layer takes 32 channels as input
#         self.conv1 = nn.Conv2d(channel, 64, kernel_size=3, stride=1, padding=1)
#         self.bn1 = nn.BatchNorm2d(64)
#
#         # One ResNet block, using 64 channels for both input and output to ensure identity connection
#         self.block = BasicBlock(64, 64, stride=1)  # No downsampling, identity connection ensured
#
#         # Calculate the flattened size for the FC layer
#         self.flattened_size = batch_size*time_step * 32 * height * width  # No downsampling, spatial dimensions unchanged
#
#         # Fully connected layer for classification
#         self.fc = nn.Linear(self.flattened_size, num_cls)
#
#     def forward(self, x):
#         # Merge the time_step into the batch dimension to handle 2D convolutions
#         batch_size, time_step, channel, height, width = x.shape
#         x = x.view(batch_size * time_step, channel, height, width)
#
#         # Apply initial convolution and ResNet block
#         x = F.relu(self.bn1(self.conv1(x)))
#         x = self.block(x)
#
#         # Reshape for FC layer
#         x = x.view(batch_size, time_step, -1)
#         x = x.mean(dim=1)  # Temporal mean pooling
#         # print(f"Shape after mean pooling: {x.shape}")
#
#         # Classification
#         x = self.fc(x)
#         return x

class ClsHead(nn.Module):
    """
    classification head that takes the dense representation from the TAP model as input,
    output raw scores for each class of interest: (nothing of interest, cell division, cell death)
    architecture: fully connected layer [TBD]
    """
    def __init__(self, input_shape, num_cls):
        super(ClsHead, self).__init__()

        batch_size, time_step, channel, height, width = input_shape
        # input shape (Batch, Time, Channel, X, Y)
        self.flattened_size = time_step*channel*height*width

        # using a fully connected layer
        self.fc = nn.Linear(self.flattened_size, num_cls)

    def forward(self, x):
        x = x.view(x.size(0), -1)
        x = self.fc(x)
        return x

def _get_paths_recursive(paths: Sequence[str], level: int):
    input_rec = paths
    for i in range(level):
        new_inps = []
        for i in input_rec:
            if Path(i).is_dir():
                children = [
                    x for x in Path(i).iterdir() if x.is_dir() or x.suffix == ".tif"
                ]
                new_inps.extend(children)
            if Path(i).suffix == ".tif":
                new_inps.append(Path(i))
        input_rec = new_inps
    return input_rec

def _load_image_folder(fnames, split_start, split_end):
    import tifffile
    import numpy as np

    imgs = []
    total = len(fnames)
    start = int(total * split_start)
    end = int(total * split_end)
    fnames = fnames[start:end]
    for fname in fnames:
        if str(fname).endswith('.tif') or str(fname).endswith('.tiff'):
            img = tifffile.imread(str(fname))
        else:
            from PIL import Image
            img = np.array(Image.open(fname))
        imgs.append(img)
    return np.stack(imgs)

def _load(path, split_start, split_end, n_images=None):
    """Loads image from disk into CPU memory.

    Can be overwritten in subclass for particular datasets.

    Args:
        path(``str``):
            Dataset directory.
        split_start(``float``):
            Use only images after this fraction of the dataset. Defaults to 0.
        split_end(``float``):
            Use only images before this fraction of the dataset. Defaults to 1.
        n_images(``int``):
            Limit number of used images. Set to ``None`` to use all avaible images.

    Returns:
        Numpy array of shape(imgs, dim0, dim1, ... , dimN).
    """
    from pathlib import Path
    import tifffile

    assert split_start >= 0
    assert split_end <= 1

    inp = Path(path).expanduser()

    if inp.is_dir():
        suffixes = ("png", "jpg", "tif", "tiff")
        for s in suffixes:
            fnames = sorted(Path(inp).glob(f"*.{s}"))
            if len(fnames) > 0:
                break
        if len(fnames) == 0:
            raise ValueError(f"Could not find ay images in {inp}")

        fnames = fnames[:n_images]
        imgs = _load_image_folder(fnames, split_start, split_end)  # <---- ONLY CHANGE HERE

    elif inp.suffix == ".tif" or inp.suffix == ".tiff":
        logger.info(f"Loading {inp}")
        imgs = tifffile.imread(str(inp))
        logger.info("Done")
        print(f'imags shape : {imgs.shape}')
        assert imgs.ndim == 3
        imgs = imgs[int(len(imgs) * split_start) : int(len(imgs) * split_end)]
        imgs = imgs[:n_images]
    else:
        raise ValueError(
            (
                f"Cannot form a dataset from {inp}. "
                "Input should be either a path to a sequence of 2d images, a single 2d+time image, or a list of 2d np.ndarrays."
            )
        )

    return imgs

def plot_images_gray_scale(image1=None, image2=None, mask1=None, mask2=None,  save_path=None):
    import matplotlib.pyplot as plt
    if image1 is None:
        image1 = torch.zeros((1,96,96), dtype=torch.uint8)
    if image2 is None:
        image2 = torch.zeros((1,96,96), dtype=torch.uint8)
    if mask1 is None:
        mask1 = torch.zeros((1,96,96), dtype=torch.uint8)
    if mask2 is None:
        mask2 = torch.zeros((1,96,96), dtype=torch.uint8)

    image1_np = image1.squeeze().numpy()
    image2_np = image2.squeeze().numpy()
    mask1_np = mask1.squeeze().numpy()
    mask2_np = mask2.squeeze().numpy()

    fig, axes = plt.subplots(1, 4, figsize=(10, 5))

    axes[0].imshow(image1_np, cmap='gray')
    axes[0].axis('off')  # Turn off axis labels

    axes[1].imshow(image2_np, cmap='gray')
    axes[1].axis('off')

    axes[2].imshow(mask1_np, cmap='gray')
    axes[2].axis('off')

    axes[3].imshow(mask2_np, cmap='gray')
    axes[3].axis('off')

    # Show the plot
    plt.savefig(save_path)
    plt.close()
    # plt.show()

def read_data_from_file(input_file_path):
    import ast  # for safe evaluations
    import numpy as np

    # Initialize an empty list to hold the data
    loaded_data = []

    # Read the file
    with open(input_file_path, 'r') as f:
        for line in f:
            # Convert the string representation of the list back to a Python object
            item = ast.literal_eval(line.strip())

            converted_item = []
            for element in item:
                if isinstance(element, list):
                    converted_item.append(np.array(element))
                else:
                    converted_item.append(np.array([element]))

            loaded_data.append(tuple(converted_item))

    return loaded_data

def masks_prep(n_frames, masks_path, delta_frames=1):
    import numpy as np
    inputs_mask = [_get_paths_recursive(masks_path, 0)]
    masks_sequences = []
    for masks in inputs_mask:
        if isinstance(masks, (str, Path)):
            masks = _load(
                path=masks,
                split_start=0,
                split_end=1
            )
        elif isinstance(masks, (tuple, list, np.ndarray)) and isinstance(
                masks[0], np.ndarray
        ):
            masks = np.asarray(masks)
        else:
            raise ValueError(
                f"Cannot form a dataset from {masks}. "
                "Input should be either a path to a sequence of 2d images, a single 2d+time image, or a list of 2d np.ndarrays."
            )
        masks = torch.as_tensor(masks)
        for delta in [delta_frames]:
            n, k = n_frames, delta
            logger.debug(f"Creating delta {delta} crops")
            tslices = tuple(
                slice(i, i + k * (n - 1) + 1, k) for i in range(len(masks) - (n - 1) * k)
            )
            _masks_sequence = [(torch.as_tensor(masks[ss])) for ss in tslices]
            masks_sequences.extend(_masks_sequence)
    return masks_sequences

def masks_lookup(coord_x, coord_y, patch_size, time_index, imgs_masks_sequences):
    from torchvision import transforms
    if isinstance(time_index, (list, tuple)):
        return list(imgs_masks_sequences[i] for i in time_index)

    x, y = imgs_masks_sequences[time_index]
    masks_crops_1 = transforms.functional.crop(x, coord_x, coord_y, patch_size, patch_size)
    masks_crops_2 = transforms.functional.crop(y, coord_x, coord_y, patch_size, patch_size)
    return masks_crops_1, masks_crops_2

def probing_mistake_predictions(model, cls_head, test_data_loader, device):
    """
    Output mistake predictions according to the type (e.g. false positive).
    :param model:
    :param test_data:
    :param type_pred_err:
    :param num_outputs:
    :param test_data_loader: batchsize must be 1
    :return:
    """
    false_positives = []
    false_negatives = []
    logits_false_pos = []
    logits_false_neg = []
    cls_head.eval()
    with torch.no_grad():
        for datapoint in test_data_loader:
            x, y = datapoint[0].to(device), datapoint[1].to(device)
            # Forward pass through the pre-trained model to get the dense representation
            # Ensure the pre-trained model is not being updated
            rep = model.embedding(x)

            # Forward pass through the classification head
            outputs = cls_head(rep)
            _, predicted = torch.max(outputs, 1)
            datapoint.append(predicted.detach().cpu())
            # datapoint : (x_crop, event_label, label, crop_coordinates, predicted_value)
            # crop_coordinates = (torch.tensor(i), torch.tensor(j), torch.tensor(idx) (time index of the frame), TAP label)
            if (predicted == 1) and (y == 0):
                # false positive
                false_positives.append(datapoint)
                logits_false_pos.append(torch.squeeze(outputs.detach().cpu()))
            elif (predicted == 0) and (y == 1):
                false_negatives.append(datapoint)
                logits_false_neg.append(torch.squeeze(outputs.detach().cpu()))

    return false_positives, false_negatives, logits_false_pos, logits_false_neg

def probing_mistaken_preds(model, test_loader, device, is_true_positive, is_true_negative):
    false_positives = []
    false_negatives = []
    logits_false_pos = []
    logits_false_neg = []
    true_positives = []
    true_negatives = []
    logits_true_positives = []
    logits_true_negatives = []
    true_positives_coordinates = []
    true_negatives_coordinates = []
    model.eval()
    with torch.no_grad():
        for datapoint in test_loader:
            x, y = datapoint[0].to(device), datapoint[1].to(device)
            outputs = model(x)
            _, predicted = torch.max(outputs, 1)
            datapoint.append(predicted.detach().cpu())
            if (predicted == 1) and (y == 0):
                false_positives.append(datapoint)
                logits_false_pos.append(torch.squeeze(outputs.detach().cpu()))
            elif (predicted == 0) and (y == 1):
                false_negatives.append(datapoint)
                logits_false_neg.append(torch.squeeze(outputs.detach().cpu()))
            if is_true_positive:
                if (predicted == 1) and (y == 1):
                    true_positives.append(datapoint)
                    logits_true_positives.append(torch.squeeze(outputs.detach().cpu()))
            if is_true_negative:
                if (predicted == 0) and (y == 0):
                    true_negatives.append(datapoint)
                    logits_true_negatives.append(torch.squeeze(outputs.detach().cpu()))

    false_positives_coordinates = [tuple(e[1:]) for e in false_positives]
    false_negatives_coordinates = [tuple(e[1:]) for e in false_negatives]
    if is_true_positive:
        true_positives_coordinates = [tuple(e[1:]) for e in true_positives]
    if is_true_negative:
        true_negatives_coordinates = [tuple(e[1:]) for e in true_negatives]

    print(f"number of false_positives predictions: {len(false_positives_coordinates)}\n"
          f"number of false_negatives predictions: {len(false_negatives_coordinates)}\n"
          f"number of true positive predictions: {len(true_positives_coordinates)}")
    return (false_positives_coordinates, false_negatives_coordinates,
            false_positives, false_negatives, logits_false_pos, logits_false_neg,
            true_positives_coordinates, true_positives, logits_true_positives,
            true_negatives_coordinates, true_negatives, logits_true_negatives)

def count_data_points(dataloader):
    count = 0
    num_positive_event = 0
    for batch in dataloader:
        inputs, event_labels, labels = batch[0], batch[1], batch[2]
        count += inputs.size(0)  # Increment by the batch size
        num_positive_event += (event_labels == 1).sum().item()
    return count, num_positive_event

def save_output_as_txt(data, output_f_path):
    # Open a file to write the numerical data
    with open(output_f_path, 'w') as f:
        for item in data:
            # Convert the tuple to a list of numbers
            converted_item = []
            for element in item:
                if isinstance(element, torch.Tensor):
                    converted_item.append(str(element.item()))  # Extract scalar value from tensor
                elif isinstance(element, list):  # Handle list of tensors
                    for tensor in element:
                        converted_item.append(str(tensor.item()))
            line = ','.join(converted_item)
            # Write the converted item to the file
            f.write(line + '\n')

    print(f"Successfully saved to {output_f_path}")

class CellEventClassModel(nn.Module):
    def __init__(self, TAPmodel, ClsHead):
        super(CellEventClassModel, self).__init__()
        self._TAPmodel = TAPmodel
        self._ClsHead = ClsHead

    def forward(self, _input):
        z = self._TAPmodel.embedding(_input)
        y = self._ClsHead(z)
        return y

def plot_mistaken_examples(num_egs_to_show, total_number, example_set, coordinates, imgs_masks_seq, image_outdir):
    for i in range(min(num_egs_to_show, total_number)):
        image1, image2 = example_set[i][0][0][0], example_set[i][0][0][1]
        coord_x, coord_y = coordinates[i][2][0], coordinates[i][2][1]
        time_index = coordinates[i][2][2]
        time_arrow_label = coordinates[i][1]
        mask_1, mask_2 = masks_lookup(coord_x, coord_y, patch_size=48, time_index=time_index,
                                      imgs_masks_sequences=imgs_masks_seq)
        # print(f"sum of pixel values for example {i} is mask_1 {torch.sum(mask_1)}, mask_2 : {torch.sum(mask_2)},"
        #       f" time_arrow_label : {time_arrow_label}")
        if time_arrow_label == 0:
            plot_images_gray_scale(image1, image2, mask_1, mask_2,
                                   os.path.join(image_outdir,f'example_{i}.pdf'))
        elif time_arrow_label == 1:
            plot_images_gray_scale(image2, image1, mask_2, mask_1,
                                   os.path.join(image_outdir,f'example_{i}.pdf'))
    print(f"Example images saved!")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mistake_pred_dir", required=True, help="output directory for the mistaken predictions")
    parser.add_argument("--masks_path", required=True)
    parser.add_argument("--num_egs_to_show", type=int, default=10)
    parser.add_argument("--TAP_model_load_path", type=str)
    parser.add_argument("--patch_size", type=int, default=48)
    parser.add_argument("--test_data_load_path", type=str)
    parser.add_argument("--combined_model_load_dir", type=str)
    parser.add_argument("--model_id", type=str)
    parser.add_argument("--is_true_positive", action="store_true")
    parser.add_argument("--is_true_negative", action="store_true")
    parser.add_argument("--cls_head_arch", type=str, help='linear, minimal, or resnet')
    parser.add_argument("--save_data", action="store_true")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Running on", device)

    TAPmodel = tarrow.models.TimeArrowNet.from_folder(model_folder=args.TAP_model_load_path)
    TAPmodel.to(device)

    if args.cls_head_arch in ['linear', 'minimal']:
        cls_head = ClsHead(input_shape=(1, 2, 32, args.patch_size, args.patch_size), num_cls=2).to(device)
    elif args.cls_head_arch == 'resnet':
        cls_head = SimpleResNet(input_shape=(1, 2, 32, args.patch_size, args.patch_size), num_cls=2).to(device)
    else:
        raise ValueError("cls_head_arch must be 'linear', 'minimal', or 'resnet'")

    event_rec_model = CellEventClassModel(TAPmodel=TAPmodel, ClsHead=cls_head)
    model_state_path = os.path.join(args.combined_model_load_dir, f'{args.model_id}.pth')
    event_rec_model.load_state_dict(torch.load(model_state_path))
    event_rec_model.to(device)
    event_rec_model.eval()
    for param in event_rec_model.parameters():
        param.requires_grad = False

    test_data_crops_flat = torch.load(args.test_data_load_path)
    test_loader = DataLoader(
        test_data_crops_flat,
        batch_size=1,
        num_workers=0,
        drop_last=False,
        persistent_workers=False
    )
    print(f"Number of data points in test_loader: {count_data_points(test_loader)}")

    (false_positive_coordinates, false_negative_coordinates,
     false_positive_egs, false_negative_egs,
     logits_false_pos, logits_false_neg,
     true_positives_coordinates, true_positives_egs,
     logits_true_positives, true_negatives_coordinates,
     true_negatives_egs, logits_true_negatives) = probing_mistaken_preds(
        event_rec_model,
        test_loader,
        device,
        is_true_positive=args.is_true_positive,
        is_true_negative=args.is_true_negative
    )

    mistake_pred_model_id_dir = os.path.join(args.mistake_pred_dir, args.model_id)
    os.makedirs(mistake_pred_model_id_dir, exist_ok=True)

    save_output_as_txt(false_positive_coordinates,
                       output_f_path=os.path.join(mistake_pred_model_id_dir, 'false_positives_coordinates.txt'))
    save_output_as_txt(false_negative_coordinates,
                       output_f_path=os.path.join(mistake_pred_model_id_dir, 'false_negatives_coordinates.txt'))
    save_output_as_txt(logits_false_neg, os.path.join(mistake_pred_model_id_dir, 'false_negatives_logits.txt'))
    save_output_as_txt(logits_false_pos, os.path.join(mistake_pred_model_id_dir, 'false_positives_logits.txt'))

    if args.save_data:
        print('Saving false positive and false negative datapoints as .pth files...')
        torch.save(false_positive_egs, os.path.join(mistake_pred_model_id_dir, 'false_positives_egs.pth'))
        torch.save(false_negative_egs, os.path.join(mistake_pred_model_id_dir, 'false_negatives_egs.pth'))

    print(f"False positive and false negative examples saved to {mistake_pred_model_id_dir}")

    image_output_dir_false_pos = os.path.join(mistake_pred_model_id_dir, 'false_positive_image_examples')
    image_output_dir_false_neg = os.path.join(mistake_pred_model_id_dir, 'false_negative_image_examples')
    os.makedirs(image_output_dir_false_pos, exist_ok=True)
    os.makedirs(image_output_dir_false_neg, exist_ok=True)

    imgs_masks_sequences = masks_prep(n_frames=2, masks_path=args.masks_path, delta_frames=1)

    print("Plotting false positive examples!")
    plot_mistaken_examples(args.num_egs_to_show, len(false_positive_egs), false_positive_egs,
                          false_positive_coordinates, imgs_masks_sequences, image_output_dir_false_pos)

    print("Plotting false negative examples!")
    plot_mistaken_examples(args.num_egs_to_show, len(false_negative_egs), false_negative_egs,
                          false_negative_coordinates, imgs_masks_sequences, image_output_dir_false_neg)

    if args.is_true_positive:
        save_output_as_txt(true_positives_coordinates,
                           output_f_path=os.path.join(mistake_pred_model_id_dir, 'true_positives_coordinates.txt'))
        if args.save_data:
            print('Saving true positive datapoints as .pth file...')
            torch.save(true_positives_egs, os.path.join(mistake_pred_model_id_dir, 'true_positives_egs.pth'))
        save_output_as_txt(logits_true_positives, os.path.join(mistake_pred_model_id_dir, 'true_positives_logits.txt'))

        image_output_dir_true_pos = os.path.join(mistake_pred_model_id_dir, 'true_positive_image_examples')
        os.makedirs(image_output_dir_true_pos, exist_ok=True)
        print("Plotting true positive examples!")
        plot_mistaken_examples(args.num_egs_to_show, len(true_positives_egs), true_positives_egs,
                              true_positives_coordinates, imgs_masks_sequences, image_output_dir_true_pos)

    if args.is_true_negative:
        save_output_as_txt(true_negatives_coordinates,
                           output_f_path=os.path.join(mistake_pred_model_id_dir, 'true_negatives_coordinates.txt'))
        if args.save_data:
            print('Saving true negative datapoints as .pth file...')
            torch.save(true_negatives_egs, os.path.join(mistake_pred_model_id_dir, 'true_negatives_egs.pth'))
        save_output_as_txt(logits_true_negatives, os.path.join(mistake_pred_model_id_dir, 'true_negatives_logits.txt'))

        image_output_dir_true_neg = os.path.join(mistake_pred_model_id_dir, 'true_negative_image_examples')
        os.makedirs(image_output_dir_true_neg, exist_ok=True)
        print("Plotting true negative examples!")
        plot_mistaken_examples(args.num_egs_to_show, len(true_negatives_egs), true_negatives_egs,
                              true_negatives_coordinates, imgs_masks_sequences, image_output_dir_true_neg)

    #### --- NEW: Line plots for FP/TP/GT+ and FN/TN/GT- per frame as in your screenshot --- ####
    import matplotlib.pyplot as plt
    import numpy as np

    def extract_frame_indices(coords):
        # coords: list of tuples, where 3rd item is crop_coordinates, whose 3rd item is the frame index
        frames = []
        for tup in coords:
            crop_coordinates = tup[2]
            frame = crop_coordinates[2]
            if isinstance(frame, torch.Tensor):
                frame = frame.item()
            frames.append(frame)
        return np.array(frames, dtype=int)

    # Extract frame indices
    fp_frames = extract_frame_indices(false_positive_coordinates)
    fn_frames = extract_frame_indices(false_negative_coordinates)
    tp_frames = extract_frame_indices(true_positives_coordinates) if args.is_true_positive else np.array([])
    tn_frames = extract_frame_indices(true_negatives_coordinates) if args.is_true_negative else np.array([])

    # Extract GT frames for positives and negatives
    # Note: test_data_crops_flat is a dataset object, so we must extract label and frame info
    all_gt_frames_pos = []
    all_gt_frames_neg = []
    for crop in test_data_crops_flat:
        # crop: (inputs, event_label, label, crop_coordinates)
        label = crop[1]
        frame = crop[3][2]
        if isinstance(frame, torch.Tensor):
            frame = frame.item()
        if label == 1:
            all_gt_frames_pos.append(frame)
        else:
            all_gt_frames_neg.append(frame)
    all_gt_frames_pos = np.array(all_gt_frames_pos, dtype=int)
    all_gt_frames_neg = np.array(all_gt_frames_neg, dtype=int)

    def percent_hist(frames, total, n_frames):
        """Return percentage of items per frame index (in %)."""
        if total == 0:
            return np.zeros(n_frames)
        hist, _ = np.histogram(frames, bins=np.arange(n_frames + 1))
        return (hist / total) * 100

    n_frames = max(
        [fp_frames.max() if len(fp_frames) else 0,
         fn_frames.max() if len(fn_frames) else 0,
         tp_frames.max() if len(tp_frames) else 0,
         tn_frames.max() if len(tn_frames) else 0,
         all_gt_frames_pos.max() if len(all_gt_frames_pos) else 0,
         all_gt_frames_neg.max() if len(all_gt_frames_neg) else 0]) + 1

    # Plot false positive time distribution
    plt.figure(figsize=(7, 4))
    plt.plot(percent_hist(tp_frames, len(tp_frames), n_frames), label='true positives')
    plt.plot(percent_hist(fp_frames, len(fp_frames), n_frames), label='false positives')
    plt.plot(percent_hist(all_gt_frames_pos, len(all_gt_frames_pos), n_frames), label='ground truth positives')
    plt.xlabel('time index of frame')
    plt.ylabel('Percentage (%)')
    plt.title('Distribution of false positives by time')
    plt.legend()
    plt.tight_layout()
    fp_plot_path = os.path.join(mistake_pred_model_id_dir, 'false_positives_by_time.png')
    plt.savefig(fp_plot_path)
    plt.close()
    print(f"Saved plot: {fp_plot_path}")

    # Plot false negative time distribution
    plt.figure(figsize=(7, 4))
    plt.plot(percent_hist(tn_frames, len(tn_frames), n_frames), label='true negatives')
    plt.plot(percent_hist(fn_frames, len(fn_frames), n_frames), label='false negatives')
    plt.plot(percent_hist(all_gt_frames_neg, len(all_gt_frames_neg), n_frames), label='ground truth negatives')
    plt.xlabel('time index of frame')
    plt.ylabel('Percentage (%)')
    plt.title('Distribution of false negatives by time')
    plt.legend()
    plt.tight_layout()
    fn_plot_path = os.path.join(mistake_pred_model_id_dir, 'false_negatives_by_time.png')
    plt.savefig(fn_plot_path)
    plt.close()
    print(f"Saved plot: {fn_plot_path}")

if __name__ == '__main__':
    main()
