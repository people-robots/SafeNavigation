#!/usr/bin/python

## @package Game
#

import pygame	as PG
import numpy	as np

from Environment import Environment
from Robot import Robot, RobotStats
from Radar import Radar
from Target import Target
import time


## Handles the main game loop
#
# This class manages the simulation. It handles the pygame window and
# events, and holds the game loop that controls the execution of the
# simulation.
#
class Game:
	## Constructor
	#
	# Initializes the game.
	#
	# @param cmdargs (object)
	# <br>	-- A command-line arguments storage object generated by
	# 	`argparse`.
	#
	def __init__(self, cmdargs):
		PG.init()
		self._cmdargs	   = cmdargs

		self._display_every_frame = True
		if cmdargs.batch_mode and not cmdargs.display_every_frame:
			self._display_every_frame = False

		self._is_paused = False
		self._doing_step = False

		self._step_num = 0;

		# Initialize the game display to 800x600
		self._gameDisplay = PG.display.set_mode((800, 600))

		# Init environment
		self._env = Environment(self._gameDisplay.get_width(), self._gameDisplay.get_height(), cmdargs.map_name, cmdargs=cmdargs)
		self._target = Target((740,50))

		# Init robots
		radar = Radar(self._env, resolution = cmdargs.radar_resolution);
		initial_position = np.array([50, 550]);
		self._normal_robot  = Robot (self._target, initial_position, radar, cmdargs, using_safe_mode =False, name="NormalRobot")
		self._safe_robot    = Robot (self._target, initial_position, radar, cmdargs, using_safe_mode = True, name="SafeRobot")
		self._robot_list    = [self._normal_robot, self._safe_robot]

		# Set window title
		PG.display.set_caption(cmdargs.window_title)


	## Handles pygame events.
	#
	# Processes any received keypresses or mouse clicks.
	#
	def handle_pygame_events(self):
		for event in PG.event.get():
			if event.type == PG.QUIT:
				return 1
			elif event.type == PG.KEYDOWN:
				if event.key == PG.K_u:
					self.update_game_image()
					self.render_game_image()
				elif event.key == PG.K_q:
					return 1
				elif event.key == PG.K_e:
					self._display_every_frame = (not self._display_every_frame)
				elif event.key == PG.K_p:
					self._is_paused = not self._is_paused;
				elif event.key == PG.K_s:
					self._doing_step = True
		return 0


	## Draws the game image
	#
	# It should be noted that this method does not call
	# `pygame.display.update()`, so the drawn screen is not yet
	# visible to the user. This is done for performance reasons, as
	# rendering the image to the screen is somewhat expensive and does
	# not always need to be done.
	#
	def update_game_image(self):
		self._env.update_display(self._gameDisplay);
		self._env.update_grid_data_from_display(self._gameDisplay)
		self._target.draw(self._gameDisplay)
		for robot in self._robot_list:
			robot.draw(self._gameDisplay)

	## Renders the stored game image onto the screen, to make it
	# visible to the user.
	#
	def render_game_image(self):
		PG.display.update()


	## The game loop used for normal execution.
	# 
	# Broadly, the game loop consists of the following steps:
	# <br>	1. Check for any user input events and process them.
	# <br>	2. Have each robot do a game step, allowing them to
	# 	process their next action and move.
	# <br>	3. Have the environment do a game step to update dynamic
	# 	obstacles.
	# <br>	4. Check exit conditions (have all robots reached the
	# 	goal?).
	# <br>	5. Create and display the game image.
	#
	def standard_game_loop(self):
		clock = PG.time.Clock()
		self._step_num = 0
		while True:
			# Handle events
			event_status = self.handle_pygame_events()
			if event_status == 1:
				return

			if self._is_paused and not self._doing_step:
				clock.tick(10);
				continue
			self._doing_step = False

			allBotsAtTarget = True

			# Process robot actions
			for robot in self._robot_list:
				if not (robot.distanceToTarget() < 20):
					allBotsAtTarget = False
					robot.NextStep(self._env.grid_data)

			# Step the environment
			self._env.next_step()

			if (self._cmdargs.batch_mode) and (allBotsAtTarget):
				return
			if not allBotsAtTarget:
				self._step_num += 1
			if self._cmdargs.max_steps <= self._step_num:
				return

			# Draw everything
			if self._display_every_frame:
				self.update_game_image()
				self.render_game_image()

			# Tick the clock
			clock.tick(self._cmdargs.max_fps)


	## A reduced game loop that is much faster for static maps.
	# 
	# This game loop does not step the environment or update the game
	# image, so it is much faster than the standard loop. It should
	# not be used for maps with dynamic obstacles or in cases where
	# viewing the progress is desired, but it is highly performant for
	# static maps in batch runs.
	#
	def fast_computing_game_loop(self):
		safe_robot_at_target = False
		normal_robot_at_target = False 
		allRobotsAtTarget = False
		step_num = 0
		while (not allRobotsAtTarget):
			allBotsAtTarget = True

			# Process robot actions
			for robot in self._robot_list:
				if not (robot.distanceToTarget() < 20):
					allBotsAtTarget = False
					robot.NextStep(self._env.grid_data)
			step_num += 1
			if self._cmdargs.max_steps <= step_num:
				return

	## Creates a result summary in CSV form
	#
	# @returns (string)
	# <br>	Format: field1,field2,...,fieldn
	# <br>	-- A CSV-formatted collection of fields representing
	# 	information about the run.
	#
	def make_csv_line(self):
		output_csv = str(self._cmdargs.speedmode) + ','
		output_csv += str(self._cmdargs.radar_resolution) +','
		output_csv += str(self._cmdargs.radar_noise_level) +','
		output_csv += str(self._cmdargs.robot_movement_momentum) +','
		output_csv += str(self._cmdargs.robot_memory_sigma) +','
		output_csv += str(self._cmdargs.robot_memory_decay) +','
		output_csv += str(self._cmdargs.robot_memory_size) +','
		output_csv += str(self._cmdargs.map_name) +','
		output_csv += str(self._cmdargs.map_modifier_num) +','
		output_csv += str(self._cmdargs.target_distribution_type) +','
		output_csv += str(self._cmdargs.use_integer_robot_location) +','

		normal_robot_stats = self._normal_robot.get_stats()
		safe_robot_stats = self._safe_robot.get_stats()

		output_csv += str(normal_robot_stats.num_collisions) + ","
		output_csv += str(safe_robot_stats.num_collisions) + ","

		output_csv += str(self._normal_robot.stepNum if self.check_robot_at_target(self._normal_robot) else "") + ","
		output_csv += str(self._safe_robot.stepNum if self.check_robot_at_target(self._safe_robot) else "") + ","

		output_csv += str(0 if self.check_robot_at_target(self._normal_robot) else 1) + ","
		output_csv += str(0 if self.check_robot_at_target(self._safe_robot) else 1) 


		return output_csv


	## Checks if the robot is at the target
	#
	# @returns (boolean)
	# <br>	-- `True` if the robot is in the target zone, `False`
	# 	otherwise.
	#
	def check_robot_at_target(self, robot):
		return robot.distanceToTarget() < 20


	## Runs the game
	#
	# This method dispatches the appropriate game loop based on the
	# command line arguments, and then prints the results as CSV when
	# finished.
	#
	def GameLoop(self):
		time.sleep(self._cmdargs.start_delay)
		if self._cmdargs.fast_computing:
			self.fast_computing_game_loop()
		else:
			self.standard_game_loop()

		print(self.make_csv_line());

		PG.quit()
		return 0
