
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import  copy
from torch.distributions.normal import Normal
from utils import ReplayBuffer, seed_everything

LOG_STD_MAX = 2
LOG_STD_MIN = -5

class DoubleSoftQNetwork(nn.Module):
    def __init__(self, input_dim, nn_hidden_size):
        super().__init__()
        
        self.Q1 = nn.Sequential(
            nn.Linear(input_dim, nn_hidden_size),
            nn.ReLU(),
            nn.Linear(nn_hidden_size, nn_hidden_size),
            nn.ReLU(),
            nn.Linear(nn_hidden_size, 1)
        )
        
        self.Q2 = nn.Sequential(
            nn.Linear(input_dim, nn_hidden_size),
            nn.ReLU(),
            nn.Linear(nn_hidden_size, nn_hidden_size),
            nn.ReLU(),
            nn.Linear(nn_hidden_size, 1)
        )

    def forward(self, x, a):
        x = torch.cat([x, a], 1)
        return self.Q1(x), self.Q2(x)
    
class SAC(object):
    def __init__(self, args, obs_dim, act_dim, action_low, action_high, device):
        seed_everything(args.seed)
        self.interact = "OFF_POLICY"
        self.device = device
        self.obs_dim, self.act_dim = obs_dim, act_dim
        self.hidden_size = args.nn_hidden_size
        self.train_batch_size = args.batch_size
        self.gamma = args.gamma
        self.temperature_opt = args.temperature_opt
        self.tau = args.tau
        # Optional gradient-norm clipping (None = disabled, preserves original behavior)
        self.max_grad_norm = getattr(args, "max_grad_norm", None)
        
        self.Q_losses = []
        self.actor_losses = []
        self.alphas = []

        if self.temperature_opt:
            self.alpha_losses = []
        
        self.Qnetworks = DoubleSoftQNetwork(obs_dim+act_dim, nn_hidden_size=self.hidden_size).to(device)
        self.target_Qnetworks = copy.deepcopy(self.Qnetworks).to(device)
        
        self.latent_pi = nn.Sequential(
            nn.Linear(obs_dim, self.hidden_size),
            nn.ReLU(),
            nn.Linear(self.hidden_size, self.hidden_size),
            nn.ReLU()).to(device)
        
        self.mu = nn.Linear(args.nn_hidden_size, act_dim).to(device)
        self.logstd = nn.Linear(args.nn_hidden_size, act_dim).to(device)
        
        self.action_scale = torch.tensor((action_high - action_low) / 2.0, dtype=torch.float32, device=device)
        self.action_bias = torch.tensor((action_high + action_low) / 2.0, dtype=torch.float32, device=device)
        
        self.q_optimizer = optim.Adam(list(self.Qnetworks.parameters()), lr=args.q_lr)
        self.actor_optimizer = optim.Adam(list(self.latent_pi.parameters())+list(self.mu.parameters())+list(self.logstd.parameters()), lr=args.policy_lr)
        
        self.buffer = ReplayBuffer(args.buffer_size, obs_dim, act_dim, device)
        self.expert_buffer = ReplayBuffer(args.buffer_size, obs_dim, act_dim, device)
        
        # Automatic entropy tuning
        if self.temperature_opt:
            self.target_entropy = -float(act_dim)
            self.log_alpha = torch.zeros(1, requires_grad=True, device=device)
            self.temp_optimizer = optim.Adam([self.log_alpha], lr=args.policy_lr)
        else:
            self.log_alpha = torch.log(torch.FloatTensor([0.2])).to(self.device)
    
    def get_action(self, obs, test=False):
        if test:
            return torch.tanh(self.mu(self.latent_pi(obs))) * self.action_scale + self.action_bias
        x = self.latent_pi(obs)
        mu = self.mu(x)
        log_std = self.logstd(x)
        log_std = LOG_STD_MIN + 0.5 * (LOG_STD_MAX - LOG_STD_MIN) * (torch.tanh(log_std) + 1)

        std = log_std.exp()
        normal = Normal(mu, std)
        x_t = normal.rsample()
        y_t = torch.tanh(x_t)
        action = y_t * self.action_scale + self.action_bias
        log_prob = normal.log_prob(x_t)
        # Enforcing Action Bound
        log_prob -= torch.log(self.action_scale * (1 - y_t.pow(2)) + 1e-6)
        log_prob = log_prob.sum(1, keepdim=True)
        return action, log_prob
    
    def store_data(self, obs, next_obs, action, reward, termination, truncation):
        reward = torch.as_tensor(reward, dtype=torch.float32, device=self.device)
        termination = torch.as_tensor(termination, dtype=torch.float32, device=self.device)
        truncation = torch.as_tensor(truncation, dtype=torch.float32, device=self.device)
        self.buffer.add(obs, next_obs, action, reward, termination, truncation)
        
    def save(self, path):
        checkpoint = {
            # model weights
            "Qnetworks_state_dict": self.Qnetworks.state_dict(),
            "target_Qnetworks_state_dict": self.target_Qnetworks.state_dict(),

            "latent_pi_state_dict": self.latent_pi.state_dict(),
            "mu_state_dict": self.mu.state_dict(),
            "logstd_state_dict": self.logstd.state_dict(),
            
            "log_alpha": self.log_alpha.detach().cpu().numpy(),
            "action_scale": self.action_scale.detach().cpu().numpy(),
            "action_bias": self.action_bias.detach().cpu().numpy(),
        }

        if self.temperature_opt:
            checkpoint["target_entropy"] = self.target_entropy

        torch.save(checkpoint, path)
        print("Model saved to:", path)

    def load(self, path):
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)

        # load network weights
        self.Qnetworks.load_state_dict(checkpoint["Qnetworks_state_dict"])
        self.target_Qnetworks.load_state_dict(checkpoint["target_Qnetworks_state_dict"])
        self.latent_pi.load_state_dict(checkpoint["latent_pi_state_dict"])
        self.mu.load_state_dict(checkpoint["mu_state_dict"])
        self.logstd.load_state_dict(checkpoint["logstd_state_dict"])
        

        # restore log_std
        with torch.no_grad():
            self.log_alpha.copy_(torch.as_tensor(checkpoint["log_alpha"], dtype=torch.float32, device=self.device))
            self.action_scale.copy_(torch.as_tensor(checkpoint["action_scale"], dtype=torch.float32, device=self.device))
            self.action_bias.copy_(torch.as_tensor(checkpoint["action_bias"], dtype=torch.float32, device=self.device))

        self.Qnetworks.to(self.device)
        self.target_Qnetworks.to(self.device)
        self.latent_pi.to(self.device)
        self.mu.to(self.device)
        self.logstd.to(self.device)
        print("Model loaded from:", path)
    
    def train(self, step, total_timesteps):
        data = self.buffer.sample(self.train_batch_size)
        with torch.no_grad():
            next_state_actions, next_state_log_pi = self.get_action(data.next_observations)
            qf1_next_target, qf2_next_target = self.target_Qnetworks(data.next_observations, next_state_actions)
            min_qf_next_target = torch.min(qf1_next_target, qf2_next_target) - self.alpha * next_state_log_pi
            next_q_value = data.rewards + (1 - data.terminations) * self.gamma * (min_qf_next_target)

        qf1_values, qf2_a_values = self.Qnetworks(data.observations, data.actions)
        qf_loss = F.mse_loss(qf1_values, next_q_value) + F.mse_loss(qf2_a_values, next_q_value)
        self.q_optimizer.zero_grad()
        qf_loss.backward()
        if self.max_grad_norm is not None:
            nn.utils.clip_grad_norm_(self.Qnetworks.parameters(), self.max_grad_norm)
        self.q_optimizer.step()

        pi, log_pi= self.get_action(data.observations)
        qf1_pi, qf2_pi = self.Qnetworks(data.observations, pi)
        min_qf_pi = torch.min(qf1_pi, qf2_pi)
        actor_loss = ((self.alpha * log_pi) - min_qf_pi).mean()
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        if self.max_grad_norm is not None:
            nn.utils.clip_grad_norm_(list(self.latent_pi.parameters()) + list(self.mu.parameters()) + list(self.logstd.parameters()), self.max_grad_norm)
        self.actor_optimizer.step()

        if self.temperature_opt:
            with torch.no_grad():
                _, log_pi = self.get_action(data.observations)
            alpha_loss = -(self.log_alpha * (log_pi + self.target_entropy).detach()).mean()

            self.temp_optimizer.zero_grad()
            alpha_loss.backward()
            self.temp_optimizer.step()

        # update the target networks
        with torch.no_grad():
            for param, target_param in zip(self.Qnetworks.parameters(), self.target_Qnetworks.parameters()):
                target_param.mul_(1 - self.tau)
                target_param.add_(self.tau * param)
        
        self.Q_losses.append(qf_loss.mean().item())
        self.actor_losses.append(actor_loss.mean().item())
        self.alphas.append(self.alpha.item())
        if self.temperature_opt:
            self.alpha_losses.append(alpha_loss.item())
            
    def logger_losses(self, step, writer):
        writer.add_scalar("losses/Q_loss", np.mean(self.Q_losses), step)
        writer.add_scalar("losses/actor_loss", np.mean(self.actor_losses), step)
        writer.add_scalar("losses/alpha", np.mean(self.alphas), step)
        if self.temperature_opt:
            writer.add_scalar("losses/alpha_loss", np.mean(self.alpha_losses), step)
            self.alpha_losses.clear()
            
        self.Q_losses.clear()
        self.actor_losses.clear()
        self.alphas.clear()
            
    @property
    def alpha(self):
        return self.log_alpha.exp()