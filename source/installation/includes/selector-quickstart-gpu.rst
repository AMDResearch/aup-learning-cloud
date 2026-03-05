.. Quick Start GPU selector — AMD device family (Radeon PRO, Radeon, Ryzen AI) and GPU model.
.. Style matches ROCm install selector; no OS, Ubuntu version, or Installation method.

.. selector:: AMD device family
   :key: family

   .. selector-option:: Radeon PRO
      :value: radeon-pro
      :width: 4

   .. selector-option:: Radeon
      :value: radeon
      :width: 4

   .. selector-option:: Ryzen AI
      :value: ryzen-ai
      :width: 4


.. selector:: Radeon PRO GPU
   :key: gpu
   :show-when: family=radeon-pro

   .. selector-info:: https://www.amd.com/en/products/graphics/workstations.html

   .. selector-option:: AI PRO R9700
      :value: ai-r9700
      :width: 3

   .. selector-option:: AI PRO R9600D
      :value: ai-r9600d
      :width: 3

.. selector:: Radeon GPU
   :key: gpu
   :show-when: family=radeon

   .. selector-info:: https://www.amd.com/en/products/graphics/desktops/radeon.html

   .. selector-option:: RX 9070 XT
      :value: rx-9070-xt
      :width: 3

   .. selector-option:: RX 9070 GRE
      :value: rx-9070-gre
      :width: 3

   .. selector-option:: RX 9070
      :value: rx-9070
      :width: 3

   .. selector-option:: RX 9060 XT LP
      :value: rx-9060-xt-lp
      :width: 3

   .. selector-option:: RX 9060 XT
      :value: rx-9060-xt
      :width: 3

   .. selector-option:: RX 9060
      :value: rx-9060
      :width: 3

.. selector:: Ryzen AI APU
   :key: gpu
   :show-when: family=ryzen-ai

   .. selector-info:: https://www.amd.com/en/products/processors/workstations/mobile.html

   .. selector-option:: Max+ PRO 395
      :value: max-pro-395
      :width: 3

   .. selector-option:: Max PRO 390
      :value: max-pro-390
      :width: 3

   .. selector-option:: Max PRO 385
      :value: max-pro-385
      :width: 3

   .. selector-option:: Max PRO 380
      :value: max-pro-380
      :width: 3

   .. selector-option:: Max+ 395
      :value: max-395
      :width: 3

   .. selector-option:: Max 390
      :value: max-390
      :width: 3

   .. selector-option:: Max 385
      :value: max-385
      :width: 3

   .. selector-option:: 9 HX 375
      :value: 9-hx-375
      :width: 3

   .. selector-option:: 9 HX 370
      :value: 9-hx-370
      :width: 3

   .. selector-option:: 9 365
      :value: 9-365
      :width: 3

.. container:: rocm-docs-install-commands

   .. code-block:: bash

      git clone https://github.com/AMDResearch/aup-learning-cloud.git
      cd aup-learning-cloud && chmod +x auplc-installer

      export GPU_TYPE=rdna4
      sudo -E ./auplc-installer install
