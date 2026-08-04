.. AUP Learning Cloud documentation master file

Welcome to AUP Learning Cloud Documentation
===========================================

AUP Learning Cloud is a tailored JupyterHub deployment designed to provide an intuitive and hands-on AI learning experience. It features a comprehensive suite of AI toolkits running on AMD hardware acceleration, enabling users to learn and experiment with ease.

.. image:: _static/images/software-stack.png
   :alt: Software Architecture
   :align: center

Choose Your Installation Path
-----------------------------

Start with the path that matches what you already have:

* **Local workstation:** Use the :doc:`Quick Start <installation/quick-start>` for a supported workstation that will run AUP Learning Cloud locally.
* **Existing Kubernetes:** Use :doc:`Deploy on an existing Kubernetes cluster <installation/existing-kubernetes>` for a running cluster that is ready for operator access.
* **New SSH-managed multi-node K3s:** Use the :doc:`multi-node K3s guide <installation/multi-node>` when each machine already has an operating system and is reachable over SSH.
* **Diskless PXE:** Use the :doc:`specialized PXE reference topology <installation/multi-node/multi-aipc-hardware-deployment>` when diskless agents must network-boot from a service machine.

.. toctree::
   :maxdepth: 2
   :caption: Introduction
   :hidden:

   introduction/overview

.. toctree::
   :maxdepth: 2
   :caption: Installation
   :hidden:

   installation/quick-start
   installation/single-node
   installation/customizing-deployment
   installation/existing-kubernetes
   installation/multi-node
   installation/multi-node/multi-aipc-hardware-deployment

.. toctree::
   :maxdepth: 1
   :caption: Learning Toolkits
   :hidden:

   Overview <learning-toolkits/index>
   learning-toolkits/computer-vision
   learning-toolkits/deep-learning
   learning-toolkits/llm-from-scratch
   learning-toolkits/physics-simulation

.. toctree::
   :maxdepth: 1
   :caption: JupyterHub Configuration
   :hidden:

   Overview <jupyterhub/index>
   jupyterhub/configuration-reference
   jupyterhub/README
   jupyterhub/authentication-guide
   jupyterhub/user-management
   jupyterhub/admin-manual
   jupyterhub/quota-system
   jupyterhub/monitoring
   jupyterhub/github-app-setup

.. toctree::
   :maxdepth: 1
   :caption: User Guide
   :hidden:

   Overview <user-guide/index>
   user-guide/platform-basics
   user-guide/jupyterlab-guide
   user-guide/code-server-guide

.. toctree::
   :maxdepth: 1
   :caption: Contributing
   :hidden:

   contributing/contributing

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
