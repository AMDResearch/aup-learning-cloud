# Large Language Model from Scratch

The LLM from Scratch toolkit takes you on a ground-up journey through every building block of a modern Large Language Model - from tensors and gradients all the way to a fully working LLaMA-style decoder trained on AMD GPUs. No black-box libraries: every component is implemented and explained step by step.

## Lab 1 - Hello World with LLaMA: LLM Inference

Get your first hands-on experience with a **pre-trained LLaMA model**: load the weights, tokenise an input prompt, and generate a response. This lab establishes the end-to-end inference workflow that later labs will build from scratch.

## Lab 2 - Deep Learning Basics

Master the **PyTorch fundamentals** that underpin every LLM: tensor creation and manipulation, computational graphs, automatic differentiation, and the mathematics of forward and backward propagation. Each concept is explicitly connected to its role inside a transformer.

## Lab 3 - Neural Network Fundamentals: Linear Layers

Explore **linear transformations** - the atomic operation inside every transformer layer. The lab covers weight matrices, bias vectors, broadcasting, and matrix multiplication, building the intuition needed to understand attention projections and feed-forward blocks.

## Lab 5a - Normalization Techniques

Understand why **normalisation** is essential for stable training of deep networks. Implement **Layer Normalization** and **RMS Normalization** from scratch, analyse their effect on gradient flow, and see how they are used inside transformer blocks.

## Lab 5b - Advanced Normalization in Transformers

Go deeper into normalisation strategies used in production LLMs. Compare **Pre-Norm vs. Post-Norm** transformer architectures, implement **sinusoidal positional encoding** with normalisation, and benchmark the approaches quantitatively - connecting everything to LLaMA and GPT designs.

## Lab 6 - Attention Mechanisms

Implement the **attention mechanism** - the core innovation of the transformer - from mathematical foundations to working code. Build Query / Key / Value projections, scaled dot-product attention, **multi-head attention**, and causal masking for autoregressive generation.

## Lab 7 - LoRA Fine-Tuning

Master **Low-Rank Adaptation (LoRA)**, the parameter-efficient fine-tuning technique that adapts billion-parameter models by training only a tiny fraction of weights. Implement LoRA layers from scratch, integrate them into attention and feed-forward blocks, and analyse the rank–performance trade-off.

## Lab 8 - Dataset Processing and Training Pipeline

Build the **complete ML pipeline** for training a language model: raw text loading, tokenisation, dataset batching, training loop with gradient accumulation, mixed-precision training, learning-rate scheduling, checkpointing, and evaluation with perplexity.

## Lab 10 - Build a Tiny LLaMA from Scratch

Put all the pieces together and build a **fully functional LLaMA-style decoder-only transformer** from scratch - RoPE positional embeddings, RMSNorm, SwiGLU feed-forward, multi-head causal attention, weight tying, and a complete training + generation loop - running end-to-end on AMD GPUs without the `transformers` library.
