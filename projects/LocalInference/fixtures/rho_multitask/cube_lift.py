# Code block 0
import numpy

home_pose()

# 1. Sample the grasp pose for the red cube.
position, quaternion = sample_grasp_pose("red cube")

# 2. Approach and grasp the cube.
goto_pose(position, quaternion, z_approach=0.05)
close_gripper()

# 3. Lift it vertically while preserving the grasp orientation.
lift_position = position + numpy.array([0.0, 0.0, 0.1])
goto_pose(lift_position, quaternion, z_approach=0.0)
