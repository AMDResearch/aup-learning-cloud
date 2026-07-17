<!-- Modifications Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->
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

# JupyterHub Helm chart

[![Documentation](https://img.shields.io/badge/Documentation-z2jh.jupyter.org-blue?logo=read-the-docs&logoColor=white)](https://z2jh.jupyter.org)
[![GitHub](https://img.shields.io/badge/Source_code-github-blue?logo=github&logoColor=white)](https://github.com/jupyterhub/zero-to-jupyterhub-k8s)
[![Discourse](https://img.shields.io/badge/Help_forum-discourse-blue?logo=discourse&logoColor=white)](https://discourse.jupyter.org/c/jupyterhub/z2jh-k8s)
[![Gitter](https://img.shields.io/badge/Social_chat-gitter-blue?logo=gitter&logoColor=white)](https://gitter.im/jupyterhub/jupyterhub)
<br>
[![Latest stable release of the Helm chart](https://img.shields.io/badge/dynamic/json.svg?label=Latest%20stable%20release&url=https://hub.jupyter.org/helm-chart/info.json&query=$.jupyterhub.stable&logo=helm&logoColor=white)](https://jupyterhub.github.io/helm-chart#jupyterhub)
[![Latest pre-release of the Helm chart](https://img.shields.io/badge/dynamic/json.svg?label=Latest%20pre-release&url=https://hub.jupyter.org/helm-chart/info.json&query=$.jupyterhub.pre&logo=helm&logoColor=white)](https://jupyterhub.github.io/helm-chart#development-releases-jupyterhub)
[![Latest development release of the Helm chart](https://img.shields.io/badge/dynamic/json.svg?label=Latest%20dev%20release&url=https://hub.jupyter.org/helm-chart/info.json&query=$.jupyterhub.latest&logo=helm&logoColor=white)](https://jupyterhub.github.io/helm-chart#development-releases-jupyterhub)

The JupyterHub Helm chart is accompanied with an installation guide at [z2jh.jupyter.org](https://z2jh.jupyter.org). Together they enable you to deploy [JupyterHub](https://jupyterhub.readthedocs.io) in a Kubernetes cluster that can make Jupyter environments available to several thousands of simultaneous users.

## History

Much of the initial groundwork for this documentation is information learned from the successful use of JupyterHub and Kubernetes at UC Berkeley in their [Data 8](http://data8.org/) program.

![](https://raw.githubusercontent.com/jupyterhub/zero-to-jupyterhub-k8s/HEAD/docs/source/_static/images/data8_massive_audience.jpg)
