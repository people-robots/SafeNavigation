#!/usr/bin/python3

import DrawTool
from Environment import Environment
from Target import Target
import time
from MDPAdapterSensor import MDPAdapterSensor

from Robot import RobotControlInput
from .AbstractNavAlgo import AbstractNavigationAlgorithm
from .LinearNavAlgo import LinearNavigationAlgorithm  
from .ValueIterationNavAlgo import ValueIterationNavigationAlgorithm, generic_value_iteration

import numpy as np
from numpy import linalg as LA
import random
import matplotlib.pyplot as plt
from matplotlib import style
import pandas as pd
import math
import Vector
import cntk as C
import os

## Maximum Entropy Deep Inverse Reinforcement Learning navigation algorithm.
# This is actually just a wrapper around another navigation algorithm, and this
# class observes the actions of the real nav algo to do inverse RL.
#
class TestCases():

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
	def __init__(self, cmdargs):
		self._maps = list(["Maps/easy_maze.png","Maps/maze.png", "Maps/double_bars.png"])
		self._targets = {0: list([(50,550),(740,50)]), 1: list([(50,550),(50,50)]), 2: list([(50,550),(50,50)])}# start position followed by goal position
		self._mdps, self._features = self._initialize_mdps(self._maps, self._targets,cmdargs, height = 600,width = 800)


	def _initialize_mdps(self, maps, targetss, cmdargs, height, width):
		mdps = list()
		features = dict()
		for i in range(len(maps)):
			targets = targetss[i]
			env = Environment(width, height, maps[i], cmdargs)
			start_point = Target(targets[0], color=0x00FF00)
			target = Target(targets[1])

			# Init robots
			mdp = MDPAdapterSensor(env, start_point.position, target.position, cell_size = 20, unique_id=os.path.basename(maps[i]))
			feature = self._get_features(mdp)
			mdps.append(mdp)
			features[mdp] = feature

		return mdps, features

	def solve_mdps(self, network, count):
		for i, mdp in enumerate(self._mdps):
			states, reward = network.forward_one_step(np.vstack(self._features[mdp].T))
			reward = list(reward.values())[0].T
			policy = self._do_value_iter(mdp,reward)
			self.plot_reward_policy(mdp,reward,policy,i,count)


	def plot_reward_policy(self, mdp, reward_map, policy, iteration, count, dpi=196.0):
		# Set up the figure
		plt.gcf().set_dpi(dpi)
		ax = plt.axes()

		# Note that we're messing with the input args here
		reward_map = reward_map.reshape(mdp._height, mdp._width)
		plt.imshow(reward_map, cmap='hot', interpolation='nearest')

		# The scale controls the size of the arrows
		scale = 0.8

		for state in mdp.states():
			# Init a dict of the values for each action
			action_values = {action:policy[state][action] for action in mdp.actions(state)}

			# avgarrow points in the average direction the robot
			# will travel based on the stochastic policy
			avgarrow_vec = np.sum(item[1]*Vector.unit_vec_from_degrees(item[0][0]) for item in action_values.items())
			avgarrow_mag = Vector.magnitudeOf(avgarrow_vec)
			avgarrow_vec = avgarrow_vec/avgarrow_mag
			ax.arrow(state[0], state[1], avgarrow_vec[0]*0.1, avgarrow_vec[1]*0.1, head_width = scale * avgarrow_mag, head_length = scale * avgarrow_mag)

			# maxarrow points in the single most likely direction
			max_action = max((item for item in action_values.items()), key=lambda item: item[1])
			maxarrow_vec = Vector.unit_vec_from_degrees(max_action[0][0])
			ax.arrow(state[0], state[1], 0.1*maxarrow_vec[0], 0.1*maxarrow_vec[1], head_width= scale * max_action[1], head_length = scale * max_action[1], color='g')

		# Output the figure to the image file
		plt.savefig('../output_data/var_{:02d}_{:02d}.png'.format(iteration, count))
		plt.close()


	def _do_value_iter(self, mdp, reward):
		def reward_func(state, action):
			return reward[0, state[1]*mdp._width + state[0]]
		return generic_value_iteration(mdp, reward_func, gamma=0.97, max_iter=1000, threshold=0.05)


	def _get_features(self, mdp):
		# in this method we retrieve the features from the mdp
		# and we transform the from a dictionary of column vectors
		# to a 2D matrix
		# each column representing the feature vector for 
		# one of the states, ordered according to the general {x,y}
		features = mdp._features
		rand_state = random.sample(mdp.states(),1)
		a_feature = features[rand_state[0]]
		feature_mat = np.zeros((a_feature.size, mdp._height* mdp._width), dtype = np.float32)
		for state in mdp.states():
			(x,y) = state
			feature_mat[:, y * mdp._width + x] = features[state]

		return feature_mat