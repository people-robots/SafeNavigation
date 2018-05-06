#!/usr/bin/python3

import numpy  as np
import Vector
from .AbstractNavAlgo import AbstractNavigationAlgorithm
from RobotControlInput import RobotControlInput
from ObstaclePredictor import CollisionConeObstaclePredictor, HMMObstaclePredictor
from queue import Queue, PriorityQueue
import Distributions
from Radar import Radar


## A navigation algorithm to be used with robots, based on trajectory 
# sampling and RRT.
#
# @see
# \ref AbstractNavAlgo.AbstractNavigationAlgorithm
# 	"AbstractNavigationAlgorithm"
#
class SamplingNavigationAlgorithm(AbstractNavigationAlgorithm):

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
	def __init__(self, sensors, target, cmdargs, params = None):
		self._sensors = sensors;
		self._cmdargs = cmdargs;
		self._target = target;

		self._params = self._get_default_params()
		if params is not None:
			for param_name in params:
				self._params[param_name] = params[param_name]

		self._radar   = self._sensors['radar'];
		self._radar_data = None
		self._dynamic_radar_data = None

		self._gps     = self._sensors['gps'];

		self._normal_speed = cmdargs.robot_speed;
		self._max_sampling_iters = self._params['max_sampling_iters']
		self._safety_threshold = self._params['safety_threshold']
		self._stepNum = 0;

		self._cur_traj = [];
		self._cur_traj_index = 0;

		self.debug_info = {
			"cur_dist": np.zeros(360),
		};

		gaussian_sigma = self._params['gaussian_sigma']
		self._gaussian = Distributions.Gaussian(sigma=gaussian_sigma, amplitude=(1/(np.sqrt(2*np.pi)*gaussian_sigma)))

		# Obstecle Predictor
		self._obstacle_predictor = CollisionConeObstaclePredictor(360, sensors['radar'].radius, 5);


	def _get_default_params(self):
		default_params = {
			'max_sampling_iters': 200,
			'safety_threshold': 0.1,
			'gaussian_sigma': 100,
		}
		return default_params


	## Next action selector method.
	#
	# @see 
	# \ref AbstractNavAlgo.AbstractNavigationAlgorithm.select_next_action
	# 	"AbstractNavigationAlgorithm.select_next_action()"
	#
	def select_next_action(self):
		self._stepNum += 1;

		# Scan the radar
		self._dynamic_radar_data = self._radar.scan_dynamic_obstacles(self._gps.location());
		self._radar_data = self._radar.scan(self._gps.location());

		# Give the current observation to the obstacle motion predictor
		self.debug_info["future_obstacles"] = self._obstacle_predictor.add_observation(self._gps.location(),
				self._radar_data,
				self._dynamic_radar_data,
				None
		);

		# Replan if the current trajectory is either finished or no 
		# longer safe
		if len(self._cur_traj) <= self._cur_traj_index or self._safety_threshold < self._safety_heuristic(self._cur_traj[self._cur_traj_index:]):
			self.debug_info["cur_dist"] = self._create_distribution_at(self._gps.location(), 0);


			# Init queue
			traj_queue = Queue();
			for i in range(self._max_sampling_iters):
				traj_queue.put_nowait(self._gen_trajectory(self._gps.location(), length=2));

			best_traj = [self._gps.location()];

			# Choose the best trajectory
			while not traj_queue.empty():
				traj = traj_queue.get_nowait();
				comp_result = self._compare_trajectories(traj, best_traj);
				if comp_result < 0:
					best_traj = traj;
			self._cur_traj = best_traj;
			self._cur_traj_index = 0;

		# Set the robot to head towards the next point along the trajectory
		next_point = self._cur_traj[self._cur_traj_index];
		self._cur_traj_index += 1;
		direction = Vector.degrees_between(self._gps.location(), next_point);
		speed = Vector.distance_between(self._gps.location(), next_point);

		if np.array_equal(next_point, self._gps.location()):
			# Next point is equal to current point, so stop the
			# robot
			return RobotControlInput(0, 0);

		return RobotControlInput(speed, direction);


	## Compares two trajectories
	#
	# @return (int)
	# <br>	`< 0` if traj1 is better than traj2
	# <br>	`0` if equally good
	# <br>	`> 0` if traj1 is worse than traj2
	#
	def _compare_trajectories(self, traj1, traj2):
		traj1_empty = (len(traj1) == 0)
		traj2_empty = (len(traj2) == 0)
		if traj1_empty and traj2_empty:
			return 0;
		elif traj1_empty:
			return 1;
		elif traj2_empty:
			return -1;


		safety1 = self._safety_heuristic(traj1);
		safety2 = self._safety_heuristic(traj2);

		if self._safety_threshold < safety1 and self._safety_threshold < safety2:
			return int(np.sign(safety1 - safety2));
		elif self._safety_threshold < safety1:
			return 1;
		elif self._safety_threshold < safety2:
			return -1;

		distance_h1 = self._eval_distance_heuristic(traj1);
		distance_h2 = self._eval_distance_heuristic(traj2);
		safety_bias = 0.5;
		heuristic1 = (1-safety_bias)*distance_h1 + safety_bias*safety1;
		heuristic2 = (1-safety_bias)*distance_h2 + safety_bias*safety2;
		return int(np.sign(heuristic1 - heuristic2));


	def _gen_trajectory(self, start_point, length=1):
		new_traj = [];
		last_point = start_point;
		for i in range(length):
			# Create a probability distribution to sample from
			# (normalized so it sums to 1)
			pdf = self._create_distribution_at(start_point, 0);
			pdf_sum = np.sum(pdf);
			if pdf_sum != 0:
				pdf = pdf / np.sum(pdf);
			else:
				pdf = np.full(360, 1/360.0);

			# Sample the next waypoint from the distribution
			angle = np.random.choice(360, p=pdf);
			vec = Vector.unit_vec_from_radians(angle*np.pi/180) * self._normal_speed;
			waypoint = np.add(last_point, vec);
			new_traj.append(waypoint);
			last_point = waypoint;
		return new_traj;


	def _create_distribution_at(self, center, time_offset):
		combiner_func = np.minimum
		targetpoint_pdf = self._gaussian.get_distribution(Vector.degrees_between(center, self._target.position));

		# The combined PDF will store the combination of all the
		# PDFs, but for now that's just the targetpoint PDF
		combined_pdf = targetpoint_pdf;

		raw_radar_data = self._radar_data_at(center, time_offset);

		normalized_radar_data = self._gaussian.amplitude * raw_radar_data / self._radar.radius;

		# Add the obstacle distribution into the combined PDF
		combined_pdf = combiner_func(combined_pdf, normalized_radar_data);
		combined_pdf = np.maximum(combined_pdf, 0);

		return combined_pdf;


	def _radar_data_at(self, center, time_offset):
		if np.array_equal(center, self._gps.location()) and time_offset == 0:
			return self._radar_data;

		radius = self._radar.radius;
		resolution = 10
		if isinstance(self._radar, Radar):
			resolution = self._radar.resolution;
		degree_step = self._radar.get_degree_step();
		nPoints = self._radar.get_data_size();
		radar_data = np.full([nPoints], radius, dtype=np.float64);
		currentStep = 0;
		for degree in np.arange(0, 360, degree_step):
			ang_in_radians = degree * np.pi / 180;
			cos_cached = np.cos(ang_in_radians);
			sin_cached = np.sin(ang_in_radians);
			for i in np.arange(0, radius, resolution):
				x = int(cos_cached * i + center[0]);
				y = int(sin_cached * i + center[1]);
				if 0.3 < self._obstacle_predictor.get_prediction([x, y], time_offset):
					radar_data[currentStep] = i;
					break;
			currentStep = currentStep + 1;
		return radar_data;


	def _eval_distance_heuristic(self, traj):
		if len(traj) > 2:
			return 5.0
		endpoint = traj[-1];
		targetpoint = self._target.position;
		angle = Vector.degrees_between(self._gps.location(), endpoint);
		distance = Vector.distance_between(endpoint, self._gps.location());
		if distance  < 0.1:
			return 10.0;
		if angle >= 360.0:
			angle = 0;

		return 1.0 - (self.debug_info["cur_dist"][int(angle)] * 1.0) * distance / len(traj) / self._normal_speed;


	def _safety_heuristic(self, traj):
		if len(traj) == 0:
			return 0.0;
		radar_data = self._radar_data;
		dynamic_radar_data = self._dynamic_radar_data;
		safety = 1.0;
		degree_step = self._radar.get_degree_step();
		data_size = self._radar.get_data_size();
		radar_range = self._radar.radius;
		time_offset = 1;
		safety_buffer = 3;

		for waypoint in traj:

			waypoint_dist = Vector.distance_between(self._gps.location(), waypoint) + safety_buffer;
			angle_to_waypoint = Vector.degrees_between(self._gps.location(), waypoint);

			index1 = int(np.ceil(angle_to_waypoint / degree_step)) % data_size;
			index2 = int(np.floor(angle_to_waypoint / degree_step)) % data_size;

			if (radar_data[index1] <= waypoint_dist or radar_data[index2] <= waypoint_dist) and (dynamic_radar_data[index1] > radar_data[index1] and dynamic_radar_data[index2] > radar_data[index2]):
				return 1.0;

			safety *= 1.0 - self._obstacle_predictor.get_prediction(waypoint, time_offset);
			time_offset += 1;
		return 1.0 - safety;


	def _is_trajectory_feasible(self, traj):
		return self._safety_heuristic(traj) < self._safety_threshold;



## A navigation algorithm to be used with robots, based on the Dynamic Window
## Approach (DWA).
#
# @see
# \ref AbstractNavAlgo.AbstractNavigationAlgorithm
# 	"AbstractNavigationAlgorithm"
#
class DwaSamplingNavigationAlgorithm(AbstractNavigationAlgorithm):

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
	def __init__(self, sensors, target, cmdargs, params=None):
		self._sensors = sensors;
		self._cmdargs = cmdargs;
		self._target = target;

		self._params = self._get_default_params()
		if params is not None:
			for param_name in params:
				self._params[param_name] = params[param_name]


		self._radar   = self._sensors['radar'];
		self._radar_data = None
		self._dynamic_radar_data = None

		self._gps     = self._sensors['gps'];

		self._normal_speed = cmdargs.robot_speed;
		self._max_sampling_iters = 200
		self._stepNum = 0;

		# Parameters from Fox, Burgard, and Thrun's original DWA paper
		self._heading_weight = self._params['heading_weight']
		self._clearance_weight = self._params['clearance_weight']
		self._velocity_weight = self._params['velocity_weight']

		self._cur_traj = [];
		self._cur_traj_index = 0;

		self.debug_info = {};

		self._obstacle_predictor = CollisionConeObstaclePredictor(360, sensors['radar'].radius, 5);

		# Parameter to indicate how certain the obstacle predictor's
		# prediction must be for us to react to the obstacle
		self._obstacle_belief_threshold = self._params['obstacle_belief_threshold']


	def _get_default_params(self):
		return {
			'heading_weight': 2.0,
			'clearance_weight': 0.2,
			'velocity_weight': 0.2,
			'obstacle_belief_threshold': 0.3,
		};


	## Next action selector method.
	#
	# @see 
	# \ref AbstractNavAlgo.AbstractNavigationAlgorithm.select_next_action
	# 	"AbstractNavigationAlgorithm.select_next_action()"
	#
	def select_next_action(self):
		self._stepNum += 1;

		# Scan the radar
		self._dynamic_radar_data = self._radar.scan_dynamic_obstacles(self._gps.location());
		self._radar_data = self._radar.scan(self._gps.location());

		# Give the current observation to the obstacle motion predictor
		self.debug_info["future_obstacles"] = self._obstacle_predictor.add_observation(self._gps.location(),
				self._radar_data,
				self._dynamic_radar_data,
				None
		);

		# Replan if the current trajectory is either finished or no 
		# longer safe
		if len(self._cur_traj) <= self._cur_traj_index or self._score_clearance(self._cur_traj[self._cur_traj_index:]) < 101:


			# Init queue
			traj_queue = Queue();
			for i in range(self._max_sampling_iters):
				traj_queue.put_nowait(self._gen_trajectory(self._gps.location(), length=4));

			best_traj = [self._gps.location()];

			# Choose the best trajectory
			while not traj_queue.empty():
				traj = traj_queue.get_nowait();
				comp_result = self._compare_trajectories(traj, best_traj);
				if comp_result < 0:
					best_traj = traj;
			self._cur_traj = best_traj;
			self._cur_traj_index = 0;

		# Set the robot to head towards the next point along the trajectory
		next_point = self._cur_traj[self._cur_traj_index];
		self._cur_traj_index += 1;
		direction = Vector.degrees_between(self._gps.location(), next_point);

		if np.array_equal(next_point, self._gps.location()):
			# Next point is equal to current point, so stop the
			# robot
			return RobotControlInput(0, 0);

		return RobotControlInput(self._normal_speed, direction);


	## Compares two trajectories
	#
	# @return (int)
	# <br>	`< 0` if traj1 is better than traj2
	# <br>	`0` if equally good
	# <br>	`> 0` if traj1 is worse than traj2
	#
	def _compare_trajectories(self, traj1, traj2):
		traj1_empty = (len(traj1) == 0)
		traj2_empty = (len(traj2) == 0)
		if traj1_empty and traj2_empty:
			return 0;
		elif traj1_empty:
			return 1;
		elif traj2_empty:
			return -1;

		return int(np.sign(self._score_trajectory(traj2) - self._score_trajectory(traj1)));


	def _gen_trajectory(self, start_point, length=1):
		new_traj = [];
		last_point = start_point;
		angle = np.random.choice(360);
		for i in range(length):

			# Sample the next waypoint from the distribution
			vec = Vector.unit_vec_from_radians(angle*np.pi/180) * self._normal_speed;
			waypoint = np.add(last_point, vec);
			new_traj.append(waypoint);
			last_point = waypoint;
		return new_traj;


	def _score_trajectory(self, traj):
		# Weighted sum of scores
		return (  self._heading_weight   * self._score_heading(traj)
		        + self._clearance_weight * self._score_clearance(traj)
		        + self._velocity_weight  * self._score_velocity(traj)
		)


	def _score_heading(self, traj):
		target_heading = self._gps.angle_to(self._target.position)
		traj_heading = self._gps.angle_to(traj[-1])
		return 180 - abs(Vector.angle_diff_degrees(target_heading, traj_heading))


	def _score_clearance(self, traj):
		if len(traj) == 0:
			return 0.0;
		radar_data = self._radar_data;
		degree_step = self._radar.get_degree_step();
		data_size = self._radar.get_data_size();
		radar_range = self._radar.radius;
		safety_buffer = 3;
		time_offset = 1;

		cumulative_path_dist = 0
		min_radar_distance = np.max(radar_data)
		for waypoint in traj:

			raw_waypoint_dist = Vector.distance_between(self._gps.location(), waypoint)
			cumulative_path_dist += raw_waypoint_dist

			angle_to_waypoint = Vector.degrees_between(self._gps.location(), waypoint);

			index1 = int(np.ceil(angle_to_waypoint / degree_step)) % data_size;
			index2 = int(np.floor(angle_to_waypoint / degree_step)) % data_size;

			adjusted_waypoint_dist = raw_waypoint_dist + safety_buffer;
			if (radar_data[index1] <= adjusted_waypoint_dist or radar_data[index2] <= adjusted_waypoint_dist):
				min_radar_distance = min(min_radar_distance, radar_data[index1], radar_data[index2]);

			obs_belief = self._obstacle_predictor.get_prediction(waypoint, time_offset);

			# If the belief reaches the threshold, consider this point an obstacle
			if self._obstacle_belief_threshold <= obs_belief:
				min_radar_distance = min(min_radar_distance, cumulative_path_dist)

			time_offset += 1

		return min_radar_distance;


	def _score_velocity(self, traj):
		# For now, velocity is fixed, so just give a constant
		return 1
