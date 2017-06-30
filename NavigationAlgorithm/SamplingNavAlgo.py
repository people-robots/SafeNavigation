#!/usr/bin/python3

import numpy  as np
import Vector
from .AbstractNavAlgo import AbstractNavigationAlgorithm
from RobotControlInput import RobotControlInput
from ObstaclePredictor import CollisionConeObstaclePredictor, HMMObstaclePredictor
from queue import Queue, PriorityQueue
import Distributions


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
	def __init__(self, sensors, target, cmdargs):
		self._sensors = sensors;
		self._cmdargs = cmdargs;
		self._target = target;

		self._radar   = self._sensors['radar'];
		self._radar_data = None
		self._dynamic_radar_data = None

		self._gps     = self._sensors['gps'];

		self._normal_speed = cmdargs.robot_speed;
		self._max_sampling_iters = 200
		self._current_mem_bias_pdf = None
		self._safety_threshold = 0.1
		self._stepNum = 0;

		self._cur_traj = [];
		self._cur_traj_index = 0;

		self.debug_info = {
			'node_list': [],
			'drawing_pdf': np.zeros(360),
			"cur_dist": np.zeros(360),
		};

		# Memory parameters
		self.visited_points	= []
		self.memory_sigma = cmdargs.robot_memory_sigma
		self.memory_decay = cmdargs.robot_memory_decay
		self.memory_size  = cmdargs.robot_memory_size
		self._mem_bias_vec = np.array([0.7, 0.7])
		self.using_safe_mode = True

		gaussian_sigma = 100
		self._gaussian = Distributions.Gaussian(sigma=gaussian_sigma, amplitude=(1/(np.sqrt(2*np.pi)*gaussian_sigma)))

		# Obstecle Predictor
		self._obstacle_predictor = CollisionConeObstaclePredictor(360, sensors['radar'].radius, 5);


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

		# Add the current location to the memory
		if self._stepNum % 1 == 0:
			self.visited_points.append(self._gps.location());

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
		

	def _sample_child_trajectories(self, seed_traj):
		# Note: When appending to this `children` variable, we use
		# `seed_traj + new_point`, i.e. using the Python list
		# concatenation operator. This will automatically make a
		# copy of seed_traj and add the new point to that, so
		# seed_traj will be unmodified (and thus, can be reused)
		children = [];

		seed_endpoint = seed_traj[-1] if 0 < len(seed_traj) else self._gps.location();

		# Append a "straight to the goal" trajectory
		angle_to_goal = self._gps.angle_to(self._target) * np.pi / 180.0
		towards_goal = Vector.unit_vec_from_radians(angle_to_goal) * self._normal_speed;
		waypoint_towards_goal = np.add(seed_endpoint, towards_goal);
		new_traj = list(seed_traj);
		new_traj.append(waypoint_towards_goal);
		children.append(new_traj);

		# Append some random trajectories
		pdf = self._create_distribution_at(seed_endpoint, len(seed_traj));
		pdf_sum = np.sum(pdf);
		if pdf_sum != 0:
			pdf = pdf / np.sum(pdf)
		else:
			pdf = np.zeros(360)
			pdf[0] = 1
		for i in range(6):
			angle = np.random.choice(360, p=pdf)
			vec = Vector.unit_vec_from_radians(angle*np.pi/180) * self._normal_speed;
			waypoint = np.add(seed_endpoint, vec);
			new_traj = list(seed_traj);
			new_traj.append(waypoint);
			children.append(new_traj);

		return children;


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

		# Process memory
		if self._cmdargs.enable_memory:
			mem_bias_pdf = self._create_memory_bias_pdf_at(center, time_offset);

			# Add the memory distribution to the combined PDF
			combined_pdf = combiner_func(combined_pdf, mem_bias_pdf);

		combined_pdf = np.maximum(combined_pdf, 0);

		return combined_pdf;


	def _radar_data_at(self, center, time_offset):
		if np.array_equal(center, self._gps.location()) and time_offset == 0:
			return self._radar_data;

		radius = self._radar.radius;
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


	def _create_memory_bias_pdf_at(self, center, time_offset):
		if np.array_equal(center, self._gps.location()) and time_offset == 0 and self._current_mem_bias_pdf is not None:
			return self._current_mem_bias_pdf;
		# Get memory effect vector
		mem_bias_vec = self._calc_memory_bias_vector_at(center, time_offset);
		self.debug_info["last_mbv"] = mem_bias_vec;

		mem_bias_ang = Vector.degrees_between([0, 0], mem_bias_vec);
		mem_bias_mag = Vector.distance_between([0, 0], mem_bias_vec);

		# Create memory distribution based on dot product with memory vector
		mem_bias_pdf = np.cos(np.abs(mem_bias_ang - np.arange(0, 360, self._gaussian.degree_resolution)) * np.pi/180);
		mem_bias_pdf += 1 # Add 1 to get the cosine function above 0
		if np.amax(mem_bias_pdf) > 0:
			mem_bias_pdf = mem_bias_pdf / np.amax(mem_bias_pdf);

		return mem_bias_pdf;


	def _calc_memory_bias_vector_at(self, center, time_offset):
		sigma = self.memory_sigma;
		decay = self.memory_decay;
		size = int(self.memory_size);
		sigmaSquared = sigma * sigma;
		gaussian_derivative = lambda x: -x*(np.exp(-(x*x/(2*sigmaSquared))) / sigmaSquared);
		vec = np.array([0, 0], dtype='float64');
		i = size;
		for point in self.visited_points[-size:]:
			effect_vector = np.subtract(point, center);
			effect_vector = effect_vector * (decay**i) * gaussian_derivative(Vector.magnitudeOf(effect_vector));
			vec += effect_vector;
			i -= 1;
		return vec


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

