<!-- Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved. -->

# ROSCon 2026: Fine-tuning a Robot Policy (MolmoAct2 + LIBERO)

In this workshop you take a real-robot vision-language-action model (**MolmoAct2**), teach it a new
skill in a simulator (**LIBERO**) with a short **LoRA** fine-tune, and then drive the fine-tuned
policy **live in the simulator** - typing an instruction and watching a robot arm carry it out.

Everything runs in your web browser on a single AMD **Strix Halo** machine. There is **nothing to
install** on your laptop and you never need `sudo` or admin rights - just the login your organizer
gives you.

> Setting up the workshop yourself (building the image, deploying the server, hosting the files)?
> That is a different job - see **[ORGANIZER.md](ORGANIZER.md)**. This page is for attendees.

---

## Step 1 - Open the workshop server in your browser

**Do this on: your own laptop, in Chrome or Firefox.**

Your organizer will give you a web address for the workshop server. It looks like this (the part in
angle brackets is filled in by your organizer):

```
http://<address-your-organizer-gives-you>:30890/
```

Open that address, then log in with the username and password your organizer gave you.

If the page does not load, the server or the network route is not ready - tell your organizer (there
is nothing to fix on your laptop).

## Step 2 - Start your personal GPU server

**Do this on: the web page from Step 1, after you log in.**

You will see a "Server Options" page. Choose:

- **ROSCon 2026 → "Fine-tuning on GPUs"**

and click **Start**. After about a minute you land in a file browser showing a folder called
`notebooks` with two `.ipynb` files. This is your own private server with its own AMD GPU.

(Optional) To confirm the GPU is working, open a terminal with **New → Terminal** and run:

```bash
/ryzers/test_torch.sh        # confirms the GPU is visible to PyTorch (ROCm)
/ryzers/test_molmoact2.sh    # confirms the MolmoAct2 + LIBERO software imports
```

## Step 3 - Your files are already loaded (nothing to do)

**There is nothing to run here.** The base model, the training dataset, and a ready-made fine-tuned
policy (about 47 GB together) are already on the machine. The moment your server started, they were
linked into your workspace automatically - instantly, with nothing downloaded and nothing copied.

This is where they are (you do not need to touch them):

| What | Where it is in your server |
|---|---|
| Base model + datasets | `~/.cache/huggingface` |
| Ready-made fine-tuned policy | `~/checkpoints/reference/pretrained_model` |

**Only if a notebook says a file is missing** (rare): open a terminal (**New → Terminal**) and run
this once. It re-links everything, needs no `sudo`, and is safe to run again:

```bash
cd /ryzers/notebooks
scripts/fetch_assets.sh
```

## Step 4 - Run the two notebooks

**Do this on: the file browser on the left of your server.** Double-click a notebook to open it,
then use the menu **Run → Run All Cells**.

| Notebook | What it does |
|---|---|
| `finetune_molmoact2_libero.ipynb` | Checks the GPU → loads the base model → validates it on real robot data → runs a short **LoRA fine-tune** → evaluates the fine-tuned policy in the LIBERO simulator. |
| `interactive_sim_molmoact2_libero.ipynb` | Drives the fine-tuned policy **live in the simulator, right inside the notebook**. Type an instruction and watch the arm act. Works on its own - it does not need notebook 1. |

The live simulator appears **inside the notebook** - there is no extra window to open and no extra
web address to visit.

---

## Which policy runs in the demo?

By default, both the evaluation in notebook 1 (Step 5) and the live simulator use our **ready-made
fine-tuned policy** at `~/checkpoints/reference/pretrained_model` (already staged for you in
Step 3). The short fine-tune you run in notebook 1 proves the training loop works, but it is far too
short to be good on its own - so the ready-made policy is what gives a strong demo.

You can change what runs by setting any of these in a notebook cell before you run it (or just leave
them alone for the default demo):

| Setting | Default | Meaning |
|---|---|---|
| `POLICY_PATH` | (unset) | Use a specific checkpoint instead: a folder on the server **or** a Hugging Face repo id. Overrides everything below. |
| `PREFER_TRAINED` | `0` | `1` = evaluate the checkpoint your own notebook run just produced, instead of the ready-made one. |
| `SUITE` | `libero_object` | Which LIBERO task family to use. |
| `TASK_ID` | `3` | Which task within that family. |
| `STEPS` | `10` | How many fine-tune steps notebook 1 runs (raise this for real training). |
| `FT_MODE` | `lora_vlm` | Fine-tune style: `lora_vlm`, `action_expert_only`, or `full`. |

Your training results land under `~/outputs` and `~/checkpoints`. Model weights and large videos
stay on the machine and are not uploaded anywhere.
