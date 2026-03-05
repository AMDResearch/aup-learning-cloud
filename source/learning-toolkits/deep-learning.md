# Deep Learning

The Deep Learning toolkit builds up machine learning knowledge from first principles - starting with classical algorithms and progressing through neural networks, sequence models, and generative architectures - all implemented hands-on in Python and PyTorch on AMD GPUs.

## DL01 - Principal Component Analysis (PCA)

Implement **PCA from scratch** using eigendecomposition to reduce the dimensionality of the Wine dataset. Visualise how high-dimensional data can be projected onto principal components while retaining the most meaningful variance.

## DL02 - Support Vector Machine (SVM)

Apply an **SVM classifier** from scikit-learn to a non-linearly separable moon-shaped dataset using kernel functions. Tune the regularisation parameter and kernel type to achieve ≥ 0.95 test accuracy, and visualise the resulting decision boundary.

## DL03 - K-Means Clustering

Implement the **K-Means** unsupervised clustering algorithm step by step - initialisation, assignment, and centroid update - and animate how clusters evolve over iterations. Explore the effect of different values of *k* on cluster quality.

## DL04 - Decision Tree

Train and visualise a **Decision Tree classifier** on the Iris dataset using scikit-learn. Experiment with `max_depth` and splitting criteria to observe underfitting vs. overfitting, and inspect decision boundaries alongside the tree structure.

## DL05 - Regression Model

Build a **linear regression model** to predict California housing prices. Learn to preprocess features, train the model, and evaluate it with MSE, MAE, and R² metrics, then visualise predicted vs. actual prices.

## DL06 - Neural Network from Scratch

Implement a **fully-connected neural network using only NumPy** - including He initialisation, sigmoid/softmax activations, BCE/CCE loss, and backpropagation - without any deep learning framework. Apply it to binary classification (Iris) and multi-class classification (EMG hand-gesture dataset).

## DL07 - Word2Vec

Train a **Word2Vec** model on the Text8 corpus using both Skip-gram and CBOW architectures with negative sampling. Explore semantic relationships through vector arithmetic (e.g., *king − man + woman ≈ queen*) and visualise embeddings with PCA / t-SNE.

## DL08 - Basic CNN on CIFAR-10

Build and train a **basic Convolutional Neural Network** on CIFAR-10 (10 object categories) in PyTorch. The lab covers the full workflow: data loading, model construction, training loop, evaluation, and qualitative prediction visualisation.

## DL09 - Denoising AutoEncoder

Implement both an **MLP-based** and a **CNN-based AutoEncoder** to remove artificial noise from MNIST handwritten digit images. Compare the reconstruction quality of the two architectures side by side.

## DL10 - Sequence-to-Sequence (Seq2Seq) Translation

Build an **LSTM-based Seq2Seq model** for English-to-Chinese translation using a small sentence-pair dataset. The lab covers teacher forcing during training and step-by-step inference to translate unseen sentences.

## DL11 - Generative Adversarial Network (DCGAN)

Train a **Deep Convolutional GAN** on MNIST where a generator learns to synthesise realistic digit images from random noise while a discriminator learns to tell real from fake. Visualise generated samples at each epoch to watch the generator improve.

## DL12 - Transformer from Scratch

Implement a **minimal Transformer** for character-level language generation - including multi-head self-attention, layer normalisation, positional embeddings, and feed-forward blocks - entirely from scratch in PyTorch. Train it on a small text corpus and generate new text.
