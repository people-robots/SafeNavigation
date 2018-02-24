
import copy

## @package BroadcastChannel
#


class BroadcastChannel:
	def __init__(self):
		self._msg_queue = []


	def add_message(self, message, bcast_location, bcast_range, bcast_time):
		self._msg_queue.append({'msg': message, 'location': bcast_location, 'range': bcast_range, 'time': bcast_time})


	def get_messages(self):
		return copy.deepcopy(self._msg_queue)

	
	## Gets all messages that were sent after (strictly AFTER, not equal
	# to) the check_time.
	#
	def get_messages_since(self, check_time):
		messages = []
		for msg in self._msg_queue:
			if check_time < msg['time']:
				messages.append(copy.deepcopy(msg))
		return messages


	## Gets all messages that were sent at the given check_time (strictly
	# equal).
	#
	def get_messages_from_time(self, check_time):
		messages = []
		for msg in self._msg_queue:
			if check_time == msg['time']:
				messages.append(copy.deepcopy(msg))
		return messages

	def step(self):
		pass

