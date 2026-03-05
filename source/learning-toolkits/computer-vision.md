# Computer Vision

The Computer Vision toolkit provides a hands-on journey through modern image understanding techniques - from classic CNN classifiers to cutting-edge generative and tracking models - all running on AMD GPU acceleration.

## CV01 - Image Classification with CNN

Build a **Convolutional Neural Network from scratch** and train it on the CIFAR-100 dataset (100 object categories). You will implement convolutional blocks, batch normalization, dropout, and a fully connected classifier head using PyTorch, then monitor training progress through loss and accuracy curves.

## CV02 - Deep Residual Networks (ResNet-50)

Train a **ResNet-50** classifier on CIFAR-100 and explore how residual (skip) connections solve the vanishing-gradient problem in very deep networks. The lab covers Top-1/Top-5 accuracy evaluation and qualitative inspection of sample predictions.

## CV03 - Object Detection with YOLOv9

Apply **YOLOv9** ("You Only Look Once"), a state-of-the-art one-stage detector, to locate and classify multiple objects in a single forward pass. You will train the model for ~10 epochs, evaluate it on validation images, and visualize detection bounding boxes.

## CV04 - Semantic Segmentation with SegNet

Train a **SegNet encoder–decoder** on the CamVid autonomous-driving dataset to assign a class label (road, car, pedestrian, building, …) to every pixel in an image. The lab saves checkpoints and produces side-by-side comparisons of predictions vs. ground truth.

## CV05 - Segment Anything (SAM)

Run inference with Meta AI's **Segment Anything Model (SAM)**, a foundation model that generalises to any image without task-specific training. The lab covers both *automatic* (all-mask) and *prompt-based* (point/box) segmentation modes, producing coloured overlay maps.

## CV06 - Multi-Object Tracking with YOLOv8 + ByteTrack

Apply a pretrained **YOLOv8** detector combined with the **ByteTrack** association algorithm to track multiple objects across video frames, assigning each a persistent identity. No training is required - the lab focuses on end-to-end inference on custom videos.

## CV07 - Variational Autoencoder (VAE & cVAE)

Implement a **Variational Autoencoder** on MNIST to learn a probabilistic latent space, then sample from it to generate new handwritten digits. The lab also covers the **Conditional VAE (cVAE)** variant, which lets you control which digit class is generated.
