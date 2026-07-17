<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->

# Large Language Model Labs

A progressive series of 14 hands-on labs covering the full stack of Large Language Model development — from PyTorch fundamentals through transformer internals to training, inference optimization, and building a complete LLaMA-style model from scratch. All labs are designed to run on AMD GPUs.

## Lab Descriptions

### **LLM01: LLM Introduction and Inference**

- **Focus**: Getting started with Large Language Models
- **Key Learning**: Load pre-trained LLaMA/GPT-2 models, tokenize text, run autoregressive text generation
- **Implementation**: Environment setup, HuggingFace model loading, generation parameters (temperature, sampling), output decoding

### **LLM02: Forward Propagation**

- **Focus**: Tensor operations and linear layers — the forward pass building blocks
- **Key Learning**: Tensor creation/shapes/device placement, matrix multiplication, `nn.Linear`, element-wise operations, `einsum`, activation functions (ReLU, GELU, SiLU)
- **Implementation**: Tensor fundamentals, matrix multiplication variants, building linear transformations, activation function comparison

### **LLM03: Backpropagation and Autograd**

- **Focus**: The backward pass — how gradients are computed and models learn
- **Key Learning**: Chain rule, dynamic computation graphs, `grad_fn` walkthrough, manual gradient verification, hooks for gradient inspection, gradient accumulation, training loops, `detach`/`no_grad`/`inference_mode`
- **Implementation**: Forward + backward on multi-layer networks, manual vs. autograd verification for `nn.Linear`, complete training loop (y = 2x + 1), A0 exercise (derive gradients for a matrix multiplication layer)

### **LLM04: Tokenization, Input Embedding & Positional Encoding**

- **Focus**: Converting raw text into position-aware numerical representations
- **Key Learning**: HuggingFace tokenizers (encode/decode/batch), `nn.Embedding` lookup, sinusoidal positional encoding, Rotary Position Embedding (RoPE), tensor reshape operations (`view`, `transpose`, `permute`, `gather`)
- **Implementation**: Tokenizer exploration, embedding visualization, RoPE implementation with illustrative position-dependent behavior checks

### **LLM05: Normalization and FFN**

- **Focus**: Normalization techniques and feed-forward network architectures for stable transformer training
- **Key Learning**: Layer normalization, RMS normalization, gradient flow and training stability, Pre-LN vs. Post-LN, FFN design patterns (SwiGLU)
- **Implementation**: Custom normalization layers from scratch, stability comparison, FFN (SwiGLU) construction, and runnable **Pre-LN vs. Post-LN** comparisons in a mini transformer-style block (matches the notebook sections that print placement trade-offs and optional training curves)

### **LLM06: Attention Mechanisms**

- **Focus**: The core innovation behind transformers
- **Key Learning**: Q/K/V projections, scaled dot-product attention (softmax-weighted aggregation), causal masking, padding masking, Multi-Head Attention (MHA), Grouped Query Attention (GQA), and how MHA, GQA, and MQA relate in modern LLMs
- **Implementation**: Attention from scratch, attention visualization, GQA implementation, and connections to LLaMA-, Mistral-, and GPT-style architectures

### **LLM07: FlashAttention**

- **Focus**: GPU-efficient attention via memory hierarchy optimization
- **Key Learning**: GPU memory hierarchy (registers, SRAM/shared memory, L2, HBM), tiling for matrix multiplication, online softmax (numerically stable incremental computation), FlashAttention V1 & V2 IO complexity analysis
- **Implementation**: Tiled matrix multiplication demonstration, online softmax implementation, benchmarking standard attention vs. `scaled_dot_product_attention`

### **LLM08: Mixture of Experts & Numerical Precision**

- **Focus**: Sparse architectures and floating-point representations
- **Key Learning**: MoE architecture (expert networks, Top-K gating, sparse activation, load balancing), floating-point formats (FP32, FP16, BF16, FP8), and INT8/INT4 quantization with their accuracy trade-offs
- **Implementation**: MoE layer with Top-K gating from scratch, format comparison, basic quantization implementation

### **LLM09: LoRA Fine-Tuning**

- **Focus**: Parameter-efficient model adaptation
- **Key Learning**: Low-rank adaptation intuition, LoRA layer design with proper initialization, rank/alpha selection trade-offs, integration with attention and FFN layers
- **Implementation**: `LoRALayer` and `LinearWithLoRA` from scratch, parameter efficiency analysis, gradient flow verification

### **LLM10: Data Processing and Model Packaging**

- **Focus**: Data pipeline and model serialization for LLM training
- **Key Learning**: Tokenizer fundamentals (encode/decode/padding/truncation/batch), HuggingFace Datasets (load/filter/map), instruction-tuning data preprocessing, `nn.Module` / `nn.Linear` internals, model packaging (`state_dict`, `safetensors`, `from_pretrained`/`save_pretrained`), PEFT LoRA adapter loading
- **Implementation**: Alpaca dataset processing pipeline, `state_dict` save/load roundtrip, safetensors format, HuggingFace model wrapping

### **LLM11: Model Training Pipeline**

- **Focus**: Complete end-to-end LLM training workflow
- **Key Learning**: Collate functions (padding, attention masks, label masking with -100), autoregressive cross-entropy loss (label shifting, prompt masking for SFT), AdamW with weight decay groups, LR scheduling (warmup + decay), gradient accumulation, mixed-precision (AMP), evaluation metrics (perplexity), HuggingFace Trainer integration, LLaMA Factory overview
- **Implementation**: Hand-written training loop with AMP and gradient clipping, training visualization, Trainer comparison

### **LLM12: Inference and KV-Cache**

- **Focus**: LLM inference optimization — decoding strategies and KV-Cache
- **Key Learning**: Two-stage pipeline (Prefill vs. Decode), how compute and latency scale with sequence length, decoding strategies (greedy, temperature, top-k, top-p), repetition/presence/frequency penalties, KV-Cache implementation (caching projected K/V tensors), KV-Cache memory analysis
- **Implementation**: Decoding strategies from scratch, TinyLM with proper KV-Cache, speed benchmark (with vs. without cache)

### **LLM13: Sparse Attention and PagedAttention**

- **Focus**: Efficient attention for long sequences and serving
- **Key Learning**: KV-Cache memory bottleneck, sliding window attention, attention sinks (StreamingLLM), dynamic sparse patterns (MInference, Quest), PagedAttention (block-based KV memory management for serving)
- **Implementation**: Static sparse pattern implementation, attention sparsity visualization, PagedAttention concepts

### **LLM14: Build a Tiny LLaMA from Scratch**

- **Focus**: Capstone — assemble a complete LLaMA-style transformer
- **Key Learning**: LLaMA block architecture (RMSNorm, RoPE, MHA, SwiGLU MLP, residual connections), PyTorch SDPA with causal + padding masks, RoPE applied to Q/K, weight tying between embedding and LM head, end-to-end training and greedy generation
- **Implementation**: Full model from scratch (no `transformers` dependency), byte-level tokenizer, toy corpus training, text generation

## Lab Organization

The labs are organized progressively, building from foundational concepts to a complete language model:

**Foundations (LLM01–LLM03)**: Introduction to LLM inference, forward propagation (tensors, linear layers, activations), and backpropagation (autograd, computation graphs, training loops). Establishes the PyTorch fundamentals needed for everything that follows.

**Transformer Components (LLM04–LLM06)**: The core building blocks — tokenization and positional encoding (RoPE), normalization (RMSNorm) and FFN design (SwiGLU), and attention mechanisms (MHA, GQA, causal masking). After these labs, students understand every component inside a Transformer block.

**Efficiency & Adaptation (LLM07–LLM09)**: FlashAttention (GPU memory hierarchy and IO-aware attention), Mixture of Experts and numerical precision (sparse scaling, quantization), and LoRA (parameter-efficient fine-tuning). Covers the key techniques for making LLMs practical at scale.

**Training & Data (LLM10–LLM11)**: Data processing pipeline (tokenization, dataset preprocessing, model packaging) and the model training pipeline (collate functions, loss functions, optimizers, hand-written loops, HuggingFace Trainer, LLaMA Factory).

**Inference & Serving (LLM12–LLM13)**: Decoding strategies and KV-Cache optimization for efficient generation, followed by sparse attention patterns and PagedAttention for long-context and high-throughput serving.

**Capstone (LLM14)**: Build a Tiny LLaMA from scratch by putting normalization, positional encoding, attention, FFN, training, and generation together into one self-contained, working model.
