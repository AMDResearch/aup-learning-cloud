import numpy as np
import torch
import random 
import os 
from typing import NamedTuple
from tqdm import tqdm

def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.cuda.manual_seed_all(seed)

class ReplayBufferSamples(NamedTuple):
    observations: torch.Tensor
    actions: torch.Tensor
    next_observations: torch.Tensor
    terminations: torch.Tensor
    truncations: torch.Tensor
    rewards: torch.Tensor
        
class ReplayBuffer(object):
    def __init__(self, buffer_size, obs_dim, act_dim, device):

        self.buffer_size = buffer_size
        self.device = device

        self.obs = torch.zeros((buffer_size, obs_dim), dtype=torch.float32, device=device)
        self.next_obs = torch.zeros((buffer_size, obs_dim), dtype=torch.float32, device=device)
        self.actions = torch.zeros((buffer_size, act_dim), dtype=torch.float32, device=device)

        self.rewards = torch.zeros((buffer_size, 1), dtype=torch.float32, device=device)
        self.terminations = torch.zeros((buffer_size, 1), dtype=torch.float32, device=device)
        self.truncations = torch.zeros((buffer_size, 1), dtype=torch.float32, device=device)

        self.pos = 0
        self.full = False

    def add(self, obs, next_obs, action, reward, termination, truncation):
        self.obs[self.pos] = obs
        self.next_obs[self.pos] = next_obs
        self.actions[self.pos] = action

        self.rewards[self.pos] = reward
        self.terminations[self.pos] = termination
        self.truncations[self.pos] = truncation

        self.pos += 1
        if self.pos == self.buffer_size:
            self.full = True
            self.pos = 0

    def sample(self, batch_size, enc_batch=False):
        if self.full:
            if enc_batch:
                batch_inds = (torch.randint(1, self.buffer_size, (batch_size - 1,), device=self.device) + self.pos) % self.buffer_size
                batch_inds = torch.cat([batch_inds, torch.tensor([self.pos - 1], device=self.device)])
            else:
                batch_inds = (torch.randint(1, self.buffer_size, (batch_size,), device=self.device) + self.pos) % self.buffer_size
        else:
            if enc_batch:
                batch_inds = torch.randint(0, self.pos, (batch_size - 1,), device=self.device)
                batch_inds = torch.cat([batch_inds, torch.tensor([self.pos - 1], device=self.device)])
            else:
                batch_inds = torch.randint(0, self.pos, (batch_size,), device=self.device)
        return self._get_samples(batch_inds)
    
    
    def _get_samples(self, batch_inds):
        return ReplayBufferSamples(
            self.obs[batch_inds],
            self.actions[batch_inds],
            self.next_obs[batch_inds],
            self.terminations[batch_inds],
            self.truncations[batch_inds],
            self.rewards[batch_inds],
        )


class PPOBuffer(object):
    """Fixed-size on-policy rollout buffer for PPO.

    Stores one full rollout of ``num_steps`` transitions and exposes the flat
    tensors that the PPO update (GAE + clipped objective) reads back.
    """

    def __init__(self, num_steps, obs_dim, act_dim, device):
        self.num_steps = num_steps
        self.device = device

        self.obs = torch.zeros((num_steps, obs_dim), dtype=torch.float32, device=device)
        self.next_obs = torch.zeros((num_steps, obs_dim), dtype=torch.float32, device=device)
        self.actions = torch.zeros((num_steps, act_dim), dtype=torch.float32, device=device)

        self.logprobs = torch.zeros(num_steps, dtype=torch.float32, device=device)
        self.rewards = torch.zeros(num_steps, dtype=torch.float32, device=device)
        self.dones = torch.zeros(num_steps, dtype=torch.float32, device=device)
        self.values = torch.zeros(num_steps, dtype=torch.float32, device=device)
        self.next_obs_values = torch.zeros(num_steps, dtype=torch.float32, device=device)

    def store(self, step, obs, action, next_obs, reward, done, value, next_obs_value, logprob):
        self.obs[step] = obs
        self.actions[step] = action
        self.next_obs[step] = next_obs
        self.rewards[step] = reward
        self.dones[step] = done
        self.values[step] = value
        self.next_obs_values[step] = next_obs_value
        self.logprobs[step] = logprob


class EvalManager(object):
    def __init__(self, env, device, reset_seed, eval_episodes):
        super().__init__()
        self.env = env
        self.action_low, self.action_high = self.env.action_space.low, self.env.action_space.high

        if reset_seed is not None:
            self.obs, _ = self.env.reset(seed=reset_seed)
        else:
            self.obs, _ = self.env.reset()

        self.device = device
        self.eval_episodes = eval_episodes
        self.results = {}
        
    
    def evaluate(self, agent, steps, writer=None, verbose=True):
        episodic_count = 0
        rewards = 0.0
        lens = 0.0
        episode_success = False
        num_success = 0
        # evaluate
        while episodic_count < self.eval_episodes:
            with torch.inference_mode():
                actions = agent.get_action(torch.as_tensor(self.obs, dtype=torch.float32, device=self.device).unsqueeze(0), test=True)
            next_obs, reward, terminations, truncations, _ = self.env.step(np.clip(actions[0].cpu().numpy(), self.action_low, self.action_high))
            rewards += reward
            lens += 1
            self.obs = next_obs

            if hasattr(self.env, "_check_success"):
                episode_success = episode_success or self.env._check_success()
                
            if terminations or truncations:
                num_success += int(episode_success)
                self.obs, _ = self.env.reset()
                episodic_count += 1
                episode_success = False

        eval_rews, eval_lens, sucess = rewards/self.eval_episodes, lens/self.eval_episodes, num_success/self.eval_episodes

        # Record
        self.results[steps] = {"rewards": eval_rews, "lengths": eval_lens}
        if writer is not None:
            writer.add_scalar("eval/eval_rews", eval_rews, steps)
            writer.add_scalar("eval/eval_lens", eval_lens, steps)
            if hasattr(self.env, "_check_success"):
                writer.add_scalar("eval/sucess", sucess, steps)
        if verbose:
            if hasattr(self.env, "_check_success"):
                tqdm.write(f"[Eval] step={steps} | rew={eval_rews:.2f} | len={eval_lens:.1f} | acc={sucess:.1f}")
            else:
                tqdm.write(f"[Eval] step={steps} | rew={eval_rews:.2f} | len={eval_lens:.1f}")
        return eval_rews, eval_lens, sucess
    
def construct_env(env_name, seed=0, render_mode=None):
    import os
    import gymnasium as gym
    
    import robosuite as suite
    from robosuite.wrappers import GymWrapper

    mujoco_env_names = {
        "2leg_cheetah",
        "5leg_ant",
        "4leg_ant",
    }

    robosuite_tasks = {
        "Door",
    }

    # HalfCheetah has no fall/flip termination and does not penalize orientation, so
    # PPO readily converges to a "flip onto its back and paddle forward" gait that
    # scores well but looks broken. This wrapper ends the episode once the torso
    # pitches past ~90 degrees, making that reward-hack unprofitable and forcing an
    # upright running gait.
    class _FlipTerminate(gym.Wrapper):
        def __init__(self, env, max_pitch=1.5708):
            super().__init__(env)
            self.max_pitch = max_pitch

        def step(self, action):
            obs, reward, terminated, truncated, info = self.env.step(action)
            pitch = float(self.env.unwrapped.data.qpos[2])
            pitch = (pitch + np.pi) % (2 * np.pi) - np.pi  # wrap to [-pi, pi]
            if abs(pitch) > self.max_pitch:
                terminated = True
            return obs, reward, terminated, truncated, info

    # -------------------------
    # 1. MuJoCo
    # -------------------------
    if env_name in mujoco_env_names:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets/")
        if env_name == "2leg_cheetah":
            env = _FlipTerminate(gym.make("HalfCheetah-v5", render_mode=render_mode))
        elif env_name == "5leg_ant":
            env = gym.make("Ant-v5", xml_file=file_path + "5leg_ant.xml", healthy_z_range=(0.2, 1.2), render_mode=render_mode)
        elif env_name == "4leg_ant":
            env = gym.make("Ant-v5", render_mode=render_mode)
        return env, 'mujoco'

    # -------------------------
    # 2. Robosuite env
    # -------------------------
    parts = env_name.split("_")
    if len(parts) == 2 and parts[0] in robosuite_tasks:
        task, robot = parts
        env = GymWrapper(
            suite.make(
                task,
                robots=robot,
                seed=seed,
                reward_shaping=True,
                use_camera_obs=False,
                use_object_obs=True,
                has_offscreen_renderer=False,
                has_renderer=False,
                initialization_noise=None,
                hard_reset=False,
            )
        )
        return env, 'robosuite'
    raise ValueError(f"Unknown env_name: {env_name}")