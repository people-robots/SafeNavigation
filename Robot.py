#!/usr/bin/python3

## @package Robot
#


import numpy  as np
import pygame as PG
import Vector
import Geometry
import time
from pygame import gfxdraw
from Environment import ObsFlag
from RobotControlInput import RobotControlInput
import DrawTool
import sys


## Holds statistics about the robot's progress, used for reporting the
# results of the simulation.
#
class RobotStats:
	def __init__(self):
		self.num_static_collisions = 0
		self.num_dynamic_collisions = 0
		self.num_steps = 0
		self.decision_times = []

	def num_total_collisions(self):
		return self.num_static_collisions + self.num_dynamic_collisions


	def avg_decision_time(self):
		if len(self.decision_times) == 0:
			return float('nan')
		return sum(self.decision_times)/len(self.decision_times)


## A GPS sensor for robots, that can give the robot's current location.
#
#
class GpsSensor:
	def __init__(self, robot):
		self._robot = robot;

	def location(self):
		return self._robot.location;

	def angle_to(self, pos):
		return Vector.degrees_between(self._robot.location, pos);

	def distance_to(self, pos):
		return Vector.distance_between(self._robot.location, pos);


## Represents a robot attempting to navigate safely through the
# environment.
#
class Robot:

	## Constructor
	#
	# @param target (numpy array)
	# <br>	Format: `[x, y]`
	# <br>	-- The target point that the robot is trying to reach
	#
	# @param initial_position (numpy array)
	# <br>	Format: `[x, y]`
	# <br>	-- The initial position of the robot
	#
	# @param radar (`Radar` object)
	# <br>	-- A radar for the robot to use to observe the environment
	#
	# @param cmdargs (object)
	# <br>	-- A command-line arguments object generated by `argparse`.
	#
	# @param using_safe_mode (boolean)
	# <br>	-- Whether the robot should operate in "safe mode", which
	# 	slightly changes the way the navigation algorithm works.
	#
	# @param name (string)
	# <br>	-- A name for the robot, only used for the purpose of
	# 	printing debugging messages.
	#
	# @param objective (Objective object)
	# <br>	-- Objective for the robot
	#
	def __init__(self, initial_position, cmdargs, env, path_color = (0, 0, 255), name="", objective=None):
		self.location           = initial_position;
		self._cmdargs           = cmdargs;
		self._env               = env
		self._path_color        = path_color
		self.name               = name;
		self._objective         = objective

		self.speed              = cmdargs.robot_speed;
		self.stats              = RobotStats();
		self._current_speed     = self.speed
		self._movement_ang      = 0 

		self._sensors           = {};

		self._nav_algo = None;

		self._obstacle = None

		self.movement_momentum = cmdargs.robot_movement_momentum

		# Variables to store drawing and debugging info
		self._last_mmv		= np.array([0, 0])
		self._drawcoll = 0
		self._visited_points	= [np.array(self.location)]

		self.debug_info = {
			'trajectory': self._visited_points,
			'min_proximities': []
		}

		# Number of steps taken in the navigation
		self.stepNum = 0

		self._last_collision_step	= -1


	def get_obstacle(self):
		return self._obstacle


	def set_obstacle(self, obstacle):
		self._obstacle = obstacle


	def get_stats(self):
		return self.stats


	## Does one step of the robot's navigation.
	#
	# This function uses radar and location information to make a
	# decision about the robot's next action to reach the goal. Then,
	# it takes one step in the planned direction.
	#
	def next_step(self, timestep):
		# Don't bother if the robot has already achieved its objective
		if self.test_objective():
			return;

		self.stepNum += 1
		self.stats.num_steps += 1

		if not self._nav_algo:
			return;

		start_decision_time = time.perf_counter()
		control_input = self._nav_algo.select_next_action();
		self.stats.decision_times.append(time.perf_counter() - start_decision_time)

		self.debug_info['min_proximities'] = self._nav_algo.debug_info['min_proximities'] if 'min_proximities' in self._nav_algo.debug_info else []

		speed = min(control_input.speed, self.speed);
		movement_ang = control_input.angle;
		self._current_speed = speed
		self._movement_ang = movement_ang
		# Update the robot's motion based on the chosen direction
		# (uses acceleration to prevent the robot from being able
		# to instantaneously change direction, more realistic)
		accel_vec = np.array([np.cos(movement_ang * np.pi / 180), np.sin(movement_ang * np.pi / 180)], dtype='float64') * speed
		movement_vec = np.add(self._last_mmv * self.movement_momentum, accel_vec * (1.0 - self.movement_momentum))
		if Vector.magnitudeOf(movement_vec) > self.speed:
			movement_vec *= speed / Vector.magnitudeOf(movement_vec) # Set length equal to self.speed
		self._last_mmv = movement_vec

		# Update the robot's position and check for a collision
		# with an obstacle
		self.location = np.add(self.location, movement_vec)

		if self._obstacle is not None:
			self._obstacle.next_step(1)

		collision_flags = self._compute_collision_flags()
		if (collision_flags & ObsFlag.ANY_OBSTACLE):
			if self.stepNum - self._last_collision_step > 1:
				self._drawcoll = 10
				if collision_flags & ObsFlag.DYNAMIC_OBSTACLE:
					self.stats.num_dynamic_collisions += 1
				elif collision_flags & ObsFlag.STATIC_OBSTACLE:
					self.stats.num_static_collisions += 1
			self._last_collision_step = self.stepNum
			movement_vec_len = Vector.magnitudeOf(movement_vec)
			self.location = np.add(self.location, -movement_vec*1.01 + np.random.uniform(-movement_vec_len*0.007, movement_vec_len*0.007, size=2));

			if self._obstacle is not None:
				self._obstacle.next_step(1)

		self._visited_points.append(np.array(self.location))


	def _compute_collision_flags(self):
		if self._obstacle is None:
			return self._env.get_obsflags(self.location)

		# Only circular robot shapes are supported for now
		if self._obstacle.shape != 1:
			return self._env.get_obsflags(self.location)

		flags = 0

		if self._collides_with_obstacle_list(self._env.dynamic_obstacles):
			flags = flags | ObsFlag.DYNAMIC_OBSTACLE
			flags = flags | ObsFlag.ANY_OBSTACLE

		if self._collides_with_obstacle_list(self._env.static_obstacles):
			flags = flags | ObsFlag.STATIC_OBSTACLE
			flags = flags | ObsFlag.ANY_OBSTACLE

		robo_obstacles = []
		for robot in self._env.robots:
			if robot == self or robot._obstacle is None:
				continue
			robo_obstacles.append(robot._obstacle)

		if self._collides_with_obstacle_list(robo_obstacles):
			flags = flags | ObsFlag.ROBOT_OBSTACLE
			flags = flags | ObsFlag.DYNAMIC_OBSTACLE
			flags = flags | ObsFlag.ANY_OBSTACLE

		return flags


	## Checks if this robot's _obstacle collides with any of the obstacles
	# in the given list.
	#
	def _collides_with_obstacle_list(self, obstacle_list):
		for obs in obstacle_list:
			if self._collides_with_obstacle(obs):
				return True
		return False

	## Checks if this robot's _obstacle collides with the given `obstacle`
	#
	# Currently assumes this robot's _obstacle is a circle.
	#
	def _collides_with_obstacle(self, obstacle):
		if self._obstacle.shape != 1:
			raise ValueError("Currently, only circles are supported for robot _obstacles.")

		if obstacle.shape == 1:  # Circle
			return (Vector.distance_between(self._obstacle.coordinate, obstacle.coordinate) <= (self._obstacle.radius + obstacle.radius))
		elif obstacle.shape == 2:
			return Geometry.test_circle_overlaps_rect(self._obstacle.coordinate, self._obstacle.radius, obstacle.coordinate, obstacle.size)
		elif obstacle.shape == 3:
			raise ValueError("No circle-ellipse overlap test implemented.")
		elif obstacle.shape == 4:
			return Geometry.test_circle_overlaps_poly(self._obstacle.coordinate, self._obstacle.radius, obstacle.polygon.get_vertices())

		raise ValueError("Unknown obstacle shape: {}".format(obstacle.shape))

	def set_nav_algo(self, nav_algo):
		self._nav_algo = nav_algo;


	def get_sensors(self):
		return self._sensors;


	def put_sensor(self, sensor_name, sensor):
		self._sensors[sensor_name] = sensor;

	def has_given_up(self):
		return self._nav_algo.has_given_up();


	def test_objective(self):
		if self._objective is None:
			return False

		return self._objective.test(self)


	## Draws this `Robot` to the given surface
	#
	# @param dtool (`DrawTool` object)
	# <br>	-- The `DrawTool` with which to draw the robot
	#
	def draw(self, dtool):
		if self._obstacle is not None:
			dtool.set_stroke_width(0);
			dtool.set_color(self._obstacle.fillcolor);
			self._env._draw_obstacle(dtool, self._obstacle)
		dtool.set_color(self._path_color);
		dtool.set_stroke_width(2);
		dtool.draw_lineseries(self._visited_points[-1500:])

		# Draw circle representing radar range
		#dtool.draw_circle(np.array(self.location, dtype=int), int(self._sensors['radar'].radius))

		# Draw the robot's sensor observations
		dtool.set_color((0xaa, 0x55, 0xdd))
		dtool.set_stroke_width(2);
		self._draw_pdf(dtool, self._sensors['radar'].scan(self._sensors['gps'].location()))
		dtool.set_color(self._path_color)

		# Draw circle to indicate a collision
		if self._drawcoll > 0:
			dtool.set_color((255, 80, 210))
			dtool.set_stroke_width(3);
			dtool.draw_circle(np.array(self.location), 12)
			self._drawcoll = self._drawcoll - 1

		# Draw static mapper data
		if 'mapdata' in self._nav_algo.debug_info.keys() and isinstance(dtool, DrawTool.PygameDrawTool):
			pix_arr = PG.surfarray.pixels2d(dtool._pg_surface);
			pix_arr[self._nav_algo.debug_info['mapdata'] == 0b00000101] = 0xFF5555;
			del pix_arr

		# Draw predicted obstacle locations
		if "future_obstacles" in self._nav_algo.debug_info.keys():
			if self._nav_algo.debug_info["future_obstacles"]:
				for fff in self._nav_algo.debug_info["future_obstacles"]:
					for x,y in fff.keys():
						gfxdraw.pixel(dtool._pg_surface.screen, x, y, (255,0,0))

		# Draw planned path waypoints
		if "path" in self._nav_algo.debug_info.keys():
			if self._nav_algo.debug_info["path"]:
				points = [x.data[:2] for x in self._nav_algo.debug_info["path"]]
				dtool.set_color((30,30,60));
				dtool.set_stroke_width(0);
				for x,y in points:
					dtool.draw_circle((x,y), 3)

		# Draw RRT
		if "rrt_tree" in self._nav_algo.debug_info.keys() and self._nav_algo.debug_info["rrt_tree"]:
			dtool.set_color((255,0,0));
			dtool.set_stroke_width(0.11);
			for node in self._nav_algo.debug_info['rrt_tree'].toListValidNodes():
				if node.parent is None or node is None:
					continue
				dtool.draw_line((node.data[0],node.data[1]), (node.parent.data[0],node.parent.data[1]))


	def draw_radar_mask(self, mask_screen, radar_data=None):
		if radar_data is None:
			radar_data = self._sensors['radar'].scan(self._sensors['gps'].location());
		mask_dtool = DrawTool.PygameDrawTool(mask_screen)
		mask_dtool.set_color(0x00000000);
		mask_dtool.set_stroke_width(0);
		self._draw_pdf(mask_dtool, radar_data);


	def _draw_pdf(self, dtool, pdf):
		if pdf is None:
			return;
		deg_res = 360 / float(len(pdf));
		scale = 1.0;
		points = [];
		for index in np.arange(0, len(pdf), 1):
			ang = index * deg_res * np.pi / 180;
			cur_point = self.location + scale*pdf[index]*np.array([np.cos(ang), np.sin(ang)], dtype='float64');
			points.append(cur_point);
		dtool.draw_poly(points)


	## Get the distance from this robot to the target point
	#
	def distanceToTarget(self):
		return Vector.getDistanceBetweenPoints(self.target.position, self.location)

	## Get the angle from this robot to the target point
	#
	def angleToTarget(self):
		return Vector.getAngleBetweenPoints(self.location, self.target.position)

	## Get the location of this robot
	#
	def get_location(self):
		return self.location;
