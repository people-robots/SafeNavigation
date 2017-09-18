#!/usr/bin/python3

from Robot import RobotControlInput
from .LinearNavAlgo import LinearNavigationAlgorithm
from .AbstractNavAlgo import AbstractNavigationAlgorithm


## Maximum Entropy Deep Inverse Reinforcement Learning navigation algorithm.
# This is actually just a wrapper around another navigation algorithm, and this
# class observes the actions of the real nav algo to do inverse RL.
#
class InverseRLNavigationAlgorithm(AbstractNavigationAlgorithm):

	## Initializes the navigation algorithm.
	# 
	# @param sensors (dict of sensors)
	# <br>	-- the sensors that this algorithm has access to
	#
	# @param target (Target obj)
	# <br>	-- the target for the navigation
	#
	# @param cmdargs (object)
	# <br>	-- A command-line arguments object generated by `argparse`.
	# 
	def __init__(self, sensors, target, cmdargs, real_algo_init=None):
		self._sensors = sensors;
		self._target  = target;
		self._cmdargs = cmdargs;

		if real_algo_init is None:
			real_algo_init = LinearNavigationAlgorithm
		self._real_algo = real_algo_init(sensors, target, cmdargs)

		self._radar   = self._sensors['radar'];
		self._radar_data = None
		self._dynamic_radar_data = None

		self._gps     = self._sensors['gps'];


	## Select the next action for the robot
	#
	# This function uses the robot's radar and location information, as
	# well as internally stored information about previous locations,
	# to compute the next action the robot should take.
	#
	# @returns (`Robot.RobotControlInput` object)
	# <br>	-- A control input representing the next action the robot
	# 	should take.
	#
	def select_next_action(self):
		state = self._get_state();
		action = self._get_action(state);

		self._add_demonstration_step(state, action);

		return action;


	## Gets the state representation for IRL
	#
	def _get_state(self):
		return (self._gps.location(), self._radar.scan(self._gps.location()));


	## Gets the action taken by the demonstrator for IRL
	#
	def _get_action(self, state):
		# We won't actually use the "state" parameter here, since the
		# real algo can scan the radar itself to get the state. It is
		# included because it could be used if we decided to use a
		# different type of demonstrator

		return self._real_algo.select_next_action();


	## Adds a (state, action) pair to the current demonstration for the IRL
	# algorithm.
	#
	def _add_demonstration_step(self, state, action):
		# TODO: Implement this method
		pass


	def has_given_up(self):
		return False;


