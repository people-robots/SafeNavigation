#!/usr/bin/python3

## @package Robot
#


import numpy  as np
import pygame as PG
import math
from Radar import Radar
import Distributions
import Vector
import matplotlib.pyplot as plt
import time
import scipy.signal
from pygame import gfxdraw

## Represents a control input for a robot. The control consists of a speed
# and a direction, which together define a single action for the robot to
# take.
#
class RobotControlInput:
	def __init__(self, speed=0, angle=0):
		self.speed = speed;
		self.angle = angle;


## Holds statistics about the robot's progress, used for reporting the
# results of the simulation.
#
class RobotStats:
	def __init__(self):
		self.num_collisions = 0
		self.num_steps = 0


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
	def __init__(self, target, initial_position, radar, cmdargs, using_safe_mode = False, name=""):
		self._cmdargs		= cmdargs
		self.target		= target
		self.location		= initial_position
		self.speed		= cmdargs.robot_speed
		self.stats		= RobotStats()
		self.name		= name
		self.radar = radar

		from NavigationAlgorithm import FuzzyNavigationAlgorithm, SamplingNavigationAlgorithm, MultiLevelNavigationAlgorithm, DynamicRrtNavigationAlgorithm, MpRrtNavigationAlgorithm
		if using_safe_mode:
			self._nav_algo = SamplingNavigationAlgorithm(self, cmdargs);
		else:
			self._nav_algo = MpRrtNavigationAlgorithm(self, cmdargs);

		self.movement_momentum = cmdargs.robot_movement_momentum

		# Variables to store drawing and debugging info
		self._last_mmv		= np.array([0, 0])
		self._drawcoll = 0
		self._PathList	= []

		# Number of steps taken in the navigation
		self.stepNum = 0

		self._last_collision_step	= -1


	def get_stats(self):
		return self.stats


	## Does one step of the robot's navigation.
	#
	# This function uses radar and location information to make a
	# decision about the robot's next action to reach the goal. Then,
	# it takes one step in the planned direction.
	#
	def NextStep(self, grid_data):
		self.stepNum += 1
		self.stats.num_steps += 1

		control_input = self._nav_algo.select_next_action();

		speed = min(control_input.speed, self.speed);
		movement_ang = control_input.angle;

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
		new_location = np.add(self.location, movement_vec)
		if (grid_data[int(new_location[0]), int(new_location[1])] & 1):
			if self.stepNum - self._last_collision_step > 1:
				if not self._cmdargs.batch_mode:
					print('Robot ({}) glitched into obstacle!'.format(self.name))
				self._drawcoll = 10
				self.stats.num_collisions += 1
			self._last_collision_step = self.stepNum
			new_location = np.add(new_location, -movement_vec*1.01 + np.random.uniform(-.5, .5, size=2));
			if(Vector.getDistanceBetweenPoints(self.location, new_location) > 2*self.speed):
				new_location = np.add(self.location, np.random.uniform(-0.5, 0.5, size=2))

		if (self._cmdargs.use_integer_robot_location):
			new_location = np.array(new_location, dtype=int)
		self.location = new_location

		self._PathList.append(np.array(self.location, dtype=int))


	def has_given_up(self):
		return self._nav_algo.has_given_up();


	## Draws this `Robot` to the given surface
	#
	# @param screen (`pygame.Surface` object)
	# <br>	-- The surface on which to draw the robot
	#
	def draw(self, screen):
		#PG.draw.circle(screen, (0, 0, 255), np.array(self.location, dtype=int), 4, 0)
		BlueColor  = (0, 0, 255)
		GreenColor = (30, 200, 30)
		if (self._nav_algo.using_safe_mode):
			PathColor = GreenColor
		else:
			PathColor = BlueColor
		for ind, o in enumerate(self._PathList):
			if ind == len(self._PathList) - 1:
				continue
			PG.draw.line(screen,PathColor,self._PathList[ind], self._PathList[ind +1], 2)
		if (0 < self._cmdargs.debug_level):
			if self._drawcoll > 0:
				PG.draw.circle(screen, (255, 127, 127), np.array(self.location, dtype=int), 15, 1)
				self._drawcoll = self._drawcoll - 1
			# Draw line representing memory effect
			#PG.draw.line(screen, (0,255,0), np.array(self.location, dtype=int), np.array(self.location+self._last_mbv*100, dtype=int), 1)

			# Draw line representing movement
			#PG.draw.line(screen, (255,0,0), np.array(self.location, dtype=int), np.array(self.location+self._last_mmv*100, dtype=int), 1)

			# Draw circle representing radar range
			PG.draw.circle(screen, PathColor, np.array(self.location, dtype=int), self.radar.radius, 2)
#			if "node_list" in self._nav_algo.debug_info.keys():
#				for node in self._nav_algo.debug_info["node_list"]:
#					for edge in node.edges:
#						if edge.weight < 20000.0:
#							PG.draw.line(screen, (255, 255, 255), edge.from_node.pos, edge.to_node.pos, 1);
#						else:
#							pass
#				for node in self._nav_algo.debug_info["node_list"]:
#					color = (255, 128, 128);
#					if not node.visited:
#						color = (64, 255, 64)
#					PG.draw.circle(screen, color, np.array(node.pos, dtype=int), 5);
#			if 'multilevel.next_node' in self._nav_algo.debug_info.keys():
#				next_node = self._nav_algo.debug_info['multilevel.next_node'];
#				PG.draw.circle(screen, (255, 255, 64), np.array(next_node.pos, dtype=int), 5);

			# Draw distribution values around robot
			#self._draw_pdf(screen, self._nav_algo.debug_info["drawing_pdf"])

			if "future_obstacles" in self._nav_algo.debug_info.keys():
				if self._nav_algo.debug_info["future_obstacles"]:
					for fff in self._nav_algo.debug_info["future_obstacles"]:
						for x,y in fff.keys():
							gfxdraw.pixel(screen, x, y, (255,0,0))
			if "path" in self._nav_algo.debug_info.keys():
				if self._nav_algo.debug_info["path"]:
					points = [x.data[:2] for x in self._nav_algo.debug_info["path"]]
					for x,y in points:
						PG.draw.circle(screen, (0,0,0), (x,y), 2)
					#	gfxdraw.pixel(screen, x, y, (0,0,0))


	def _draw_pdf(self, screen, pdf):
		if pdf is None:
			return;
		deg_res = 360 / float(len(pdf))
		scale = 1.0#self.radar.radius
		last_point = [self.location[0] + (pdf[0] * scale), self.location[1]]
		for index in np.arange(0, len(pdf), 1):
			ang = index * deg_res * np.pi / 180
			cur_point = self.location + scale*pdf[index]*np.array([np.cos(ang), np.sin(ang)], dtype='float64')
			PG.draw.line(screen, (200, 0, 200), last_point, cur_point, 1)
			last_point = cur_point


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
