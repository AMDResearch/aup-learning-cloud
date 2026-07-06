<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.  Portions of this notebook consist of AI-generated content. -->
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


This is the Course docker file folder.  

Here has 3 kinds of courses, CV, DL, LLM. 
CV and DL are recommended to run on dGPUs, and LLM is suggested to run on 395.

Upon buiding, the scripts inside each folder will copy related notebooks from `projects`, download neccessary files,
and build then push the image.

Course images remain notebook and course focused. Browser coding environments are built from the separate generic code image line in `dockerfiles/Code/` as `auplc-code-cpu` and `auplc-code-gpu`; do not create per-course VS Code image variants such as course-specific code-server images.

Use the existing course target for course notebook images:

```bash
make -C dockerfiles courses GPU_TARGET=gfx1151
```

Course resources should land on their course content. Set each official course
resource's `custom.resources.metadata.<resource>.defaultPath` to the same path as
the image `WORKDIR`, such as `/opt/workspace/CV`. The official image contract
verifier checks that metadata and image contract:

```bash
make -C dockerfiles verify-resource-contracts
```

The verifier is for official images. At runtime, the Hub doesn't check whether a
configured path exists in arbitrary or custom images. Custom course images must
create their configured landing path themselves.

Use the code targets only for generic code-server environments:

```bash
make -C dockerfiles code-cpu
make -C dockerfiles code-gpu GPU_TARGET=gfx1151
make -C dockerfiles code
```
