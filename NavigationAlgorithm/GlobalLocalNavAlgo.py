#!/usr/bin/python3

import numpy  as np
import Vector
from .AbstractNavAlgo import AbstractNavigationAlgorithm
from .DynamicRrtNavAlgo import DynamicRrtNavigationAlgorithm
from .SamplingNavAlgo import SamplingNavigationAlgorithm
from .IntegratedEnvNavAlgo import IntegratedEnvNavigationAlgorithm
from Target import Target
from StaticMapper import StaticMapper
from . import util


def _default_global_algo_init(*args, **kwargs):
	if 'use_as_global_planner' not in kwargs:
		kwargs['use_as_global_planner'] = True
	return DynamicRrtNavigationAlgorithm(*args, **kwargs)


## A navigation algorithm to be used with robots, based on trajectory 
# sampling and RRT.
#
# @see
# \ref AbstractNavAlgo.AbstractNavigationAlgorithm
# 	"AbstractNavigationAlgorithm"
#
class GlobalLocalNavigationAlgorithm(AbstractNavigationAlgorithm):

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
	def __init__(self, sensors, target, cmdargs, params = None, global_algo_init = _default_global_algo_init, local_algo_init = SamplingNavigationAlgorithm):
		self._sensors = sensors;
		self._target  = target
		self._cmdargs = cmdargs;
		self._global_algo_init = global_algo_init;
		self._local_algo_init = local_algo_init;

		self._params = self._get_default_params()
		if params is not None:
			for param_name in params:
				self._params[param_name] = params[param_name]

		self._radar = sensors['radar'];
		self._gps   = sensors['gps'];
		sensors['mapper'] = StaticMapper(sensors);

		self.debug_info = {};

		self._waypoint_radius = 26

		self._global_algo = util.algo_from_config(self._params['global_algorithm'], sensors, target, cmdargs, use_as_global_planner=True);
		self._next_waypoint = Target(self._gps.location(), radius = self._waypoint_radius);
		self._local_algo = util.algo_from_config(self._params['local_algorithm'], sensors, self._next_waypoint, cmdargs);
		self._tmp_counter = 0;
		self._has_given_up = False


	def _get_default_params(self):
		default_params = {
			'global_algorithm': {
				'type': 'drrt',
				'params': {}
			},
			'local_algorithm': {
				'type': 'problp',
				'params': {}
			},
		}
		return default_params


	def select_next_action(self):
		rcnt = 10
		if self._tmp_counter > 30:
			self._tmp_counter = 0;
			self._global_algo = util.algo_from_config(self._params['global_algorithm'], self._sensors, self._target, self._cmdargs, use_as_global_planner=True);
			self._global_algo.select_next_action();
			if self._global_algo.has_given_up():
				self._has_given_up = True
			if len(self._global_algo._solution) == 0:
				self._next_waypoint = self._target
			else:
				self._next_waypoint = Target(np.array(self._global_algo._solution[0].data), radius=self._waypoint_radius);
			self._local_algo = util.algo_from_config(self._params['local_algorithm'], self._sensors, self._next_waypoint, self._cmdargs);
			#self._local_algo.set_target(self._next_waypoint)
		elif self._gps.distance_to(self._next_waypoint.position) < self._next_waypoint.radius or self._tmp_counter % rcnt == (rcnt-1):
			if self._gps.distance_to(self._next_waypoint.position) < self._next_waypoint.radius:
				self._tmp_counter = 0;

			old_waypoint = self._next_waypoint
			self._global_algo.select_next_action();
			if len(self._global_algo._solution) > 0:
				self._next_waypoint = Target(np.array(self._global_algo._solution[0].data), radius=self._waypoint_radius);
			else:
				self._next_waypoint = self._target

			if self._next_waypoint != old_waypoint:
				self._local_algo = util.algo_from_config(self._params['local_algorithm'], self._sensors, self._next_waypoint, self._cmdargs);
				#self._local_algo.set_target(self._next_waypoint)

		self._tmp_counter += 1;
		next_action = self._local_algo.select_next_action();
		self.debug_info = {**self._local_algo.debug_info, **self._global_algo.debug_info};
		return next_action;

	def has_given_up(self):
		return self._has_given_up

	def set_target(self, new_target):
		self._target = new_target
		self._global_algo = util.algo_from_config(self._params['global_algorithm'], self._sensors, self._target, self._cmdargs, use_as_global_planner=True);

