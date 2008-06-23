#!/usr/bin/env python

def human_byte_sizes(value):
    return human_value(value, 1024, "B")

def human_value(value, base = 1000, unit = ""):

	if value == None:
		return "-"
		
	if value >= pow(base, 3):
		return "%.1fG%s" % (value / pow(base, 3), unit)

	if value >= pow(base, 2):
		return "%.1fM%s" % (value / pow(base, 2), unit)

	if value >= base:
		return "%.1fK%s" % (value / base, unit)

	if value >= 1:
		return "%d%s" % (value, unit)
		
	if value == 0:
		return "0"
		
	if base == 1000:
		return "%dm%s" % (value * base, unit)

	return "%2.2f%s" % (value, unit)

class min_avg_max_class:

	def clear(self):

		self.min = None
		self.max = None
		self.sum = 0
		self.pushed = 0

	def __init__(self, name, value = None, base = 1000, unit = "", thread_safe = False):

		self.name = name
		self.base = base
		self.unit = unit

		self.clear()

		if thread_safe:
			from threading import Lock
			self._threadlock = Lock()
		else:
			self._threadlock = None

		if value:
			self.push(value)

	def lock_acquire(self):
		if self._threadlock:
			self._threadlock.acquire()

	def lock_release(self):
		if self._threadlock:
			self._threadlock.release()

	def push(self, value):

		if type(value) == list:
			for x in value:
				self.push(x)
			return

		value = float(value)

		self.lock_acquire()

		if self.min == None or value < self.min:
			self.min = value

		if self.max == None or value > self.max:
			self.max = value

		self.sum += value
		self.pushed += 1

		self.lock_release()
		
	def avg(self):
		try:	return float(self.sum / self.pushed)
		except:	return None

	def __str__(self):
		return """%s(min/avg/max):%s/%s/%s""" % (self.name, human_value(self.min, self.base, self.unit), human_value(self.avg(), self.base, self.unit), human_value(self.max, self.base, self.unit))

