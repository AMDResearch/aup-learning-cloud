# Physics Simulation

The Physics Simulation toolkit introduces **Genesis**, a high-performance physics engine with native AMD GPU (ROCm/HIP) support. Through four progressive labs you will go from loading your first robot to running massively parallel simulations - the foundation for modern robot learning and reinforcement training.

## PhySim01 - Hello Genesis: Load a Robot into a Scene

Set up your first **Genesis simulation environment**: initialise the AMD GPU backend, configure the simulator (time step, gravity, floor height) and visualiser (camera position, field of view, FPS), then load a robot model into the scene and step the simulation forward.

## PhySim02 - Control Your Robot

Without active control, a robot arm simply collapses under gravity. In this lab you apply **PD (Proportional–Derivative) controllers** to stabilise the arm and command it to reach target joint positions. Learn how Genesis exposes built-in controllers and how to tune gains for stable motion.

## PhySim03 - Grasping with IK and Motion Planning

Implement a complete **pick-and-place task**: use **Inverse Kinematics (IK)** to automatically compute joint angles for a target end-effector pose, then chain IK waypoints into a **motion plan** to hover above, descend to, grasp, and lift a cube.

## PhySim04 - Parallel Simulation

Scale up to **massive parallelism** by running hundreds of independent robot environments simultaneously on the GPU within a single Genesis scene. This is the key technique behind data-efficient reinforcement learning - generating thousands of experience trajectories in the time it would take to run one.
