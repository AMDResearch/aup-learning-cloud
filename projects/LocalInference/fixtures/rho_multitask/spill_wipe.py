# Code block 0
import numpy

# 1. Get the spill extents and center pose.
position, _, bbox_extent = get_object_pose("brown spill", return_bbox_extent=True)
length_x, length_y, _ = bbox_extent
center_x, center_y, _ = position
x_min = center_x - length_x / 2.0
x_max = center_x + length_x / 2.0
y_min = center_y - length_y / 2.0
y_max = center_y + length_y / 2.0

# 2. Plan and execute a dense raster wipe.
wipe_z = 0.0
wipe_quaternion = numpy.array([0.0, 0.0, 1.0, 0.0])
step_size = 0.02
print("Starting wiping motion...")

x_steps = numpy.arange(x_min, x_max + step_size, step_size)
for x in x_steps:
    y_steps_forward = numpy.arange(y_min, y_max + step_size, step_size)
    y_steps_backward = numpy.arange(y_max, y_min - step_size, -step_size)
    for y in y_steps_forward:
        goto_pose(numpy.array([x, y, wipe_z]), wipe_quaternion)
    for y in y_steps_backward:
        goto_pose(numpy.array([x, y, wipe_z]), wipe_quaternion)

print("Wiping complete.")
