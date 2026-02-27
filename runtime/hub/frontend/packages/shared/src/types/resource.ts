// Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

export interface ResourceRequirements {
  cpu: string;
  memory: string;
  memory_limit?: string;
  "amd.com/gpu"?: string;
  "amd.com/npu"?: string;
}

export interface ResourceMetadata {
  group: string;
  description: string;
  subDescription?: string;
  accelerator?: string;
  acceleratorKeys?: string[];
  allowGitClone?: boolean;
}

export interface Resource {
  key: string;
  image: string;
  requirements: ResourceRequirements;
  metadata?: ResourceMetadata;
}

export interface ResourceGroup {
  name: string;
  displayName: string;
  resources: Resource[];
}

export interface ResourcesResponse {
  resources: Resource[];
  groups: ResourceGroup[];
  acceleratorKeys: string[];
  allowedGitProviders: string[];
  githubAppName?: string;
}
