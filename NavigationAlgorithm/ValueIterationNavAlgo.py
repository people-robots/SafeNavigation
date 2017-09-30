#!/usr/bin/python3

from Robot import RobotControlInput
from .AbstractNavAlgo import AbstractNavigationAlgorithm
import numpy as np
import copy


## Value Iteration navigation algorithm
# This initially runs value iteration to get an optimal policy, then it
# executes the policy.
#
class ValueIterationNavigationAlgorithm(AbstractNavigationAlgorithm):

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

		self._mdp = sensors['mdp'];
		self._gps = sensors['gps'];
		self.debug_info = self._sensors['debug']

		self._values = {k: 0.0 for k in self._mdp.states()}
		self._values[self._mdp.goal_state()] = 1

		self._policy = self._do_value_iter()


	def _do_value_iter(self):
		mdp = self._mdp
		gamma = 0.98

		old_values = {state: 0.0 for state in self._mdp.states()}
		old_values[self._mdp.goal_state()] = 1
		new_values = old_values

		qvals = dict()
		for state in mdp.states():
			qvals[state] = dict()
			for action in mdp.actions(state):
				qvals[state][action] = 0.0

		while True:
			old_values = new_values
			new_values = dict()
			for state in mdp.states():
				for action in mdp.actions(state):
					# Fear not: this massive line is just a Bellman-ish update
					qvals[state][action] = mdp.reward(state, action, None) + gamma*sum({mdp.transition_prob(state, action, next_state)*old_values[next_state] for next_state in mdp.successors(state)})

				## Softmax to get value
				#exp_qvals = {action: np.exp(qval) for action, qval in qvals[state].items()}
				#new_values[state] = max(exp_qvals.values())/sum(exp_qvals.values())

				# Just take the max to get values
				new_values[state] = max(qvals[state].values())

			# Quit if we have converged
			if max({abs(old_values[s] - new_values[s]) for s in mdp.states()}) < 0.01:
				break

		policy = dict()
		for state in mdp.states():
			policy[state] = dict()
			exp_qvals = {action: np.exp(qval)*10 for action, qval in qvals[state].items()}
			sum_exp_qvals = sum(exp_qvals.values())
			for action in mdp.actions(state):
				#print(policy[state], exp_qvals, qvals[state])
				policy[state][action] = exp_qvals[action]/sum_exp_qvals

		return policy


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

		return RobotControlInput(action[1], action[0]);


	## Gets the state representation
	#
	def _get_state(self):
		loc = self._gps.location()
		return self._mdp.discretize(loc)


	## Gets the action based on the policy
	#
	# Since the policy is stochastic, note that this chooses a random
	# action based on the policy's probability distribution
	def _get_action(self, state):
		total = 0.0
		rand = np.random.random()
		for action in self._policy[state]:
			total += self._policy[state][action]
			if rand < total:
				return action
		return self._policy[state].keys()[0]

	## Adds a (state, action) pair to the current demonstration for the IRL
	# algorithm.
	#
	def _add_demonstration_step(self, state, action):
		# TODO: Implement this method
		pass


	def has_given_up(self):
		return False;


