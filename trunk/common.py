#!/usr/bin/env python

import os
from stat import *

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

OP_TYPE_OPEN  = 10
OP_TYPE_DUP   = 12
OP_TYPE_DUP2  = 14
OP_TYPE_FCNTL = 15
OP_TYPE_LSEEK = 16
OP_TYPE_READ  = 18
OP_TYPE_WRITE = 20
OP_TYPE_CLOSE = 22

class appdump_file:

	file_and_sizes = {}

	def __init__(self, fname):

		self.fp = open(fname, "r")

		pos = os.stat(fname)[ST_SIZE]
		step = 1024

		while True:
			pos -= step
			self.fp.seek(pos)
			buf = self.fp.read(step + 16)
			tagpos = buf.find("%files")
			if  tagpos > 0:
				self.fp.seek(pos + tagpos)

				if not self.fp.readline().startswith("%files"):
					raise "Error"

				while True:
					line = self.fp.readline().strip()

					if len(line) == 0:
						return

					line = line.split("|", 1)

					if len(line) != 2:
						continue

					self.file_and_sizes[line[0]] = int(line[1])

	def convert_args_string_to_int(self, args):

		tab = { "O_RDWR":os.O_RDWR, "O_WRONLY":os.O_WRONLY, "O_RDONLY":os.O_RDONLY, "O_NONBLOCK":os.O_NONBLOCK, "O_DIRECTORY":os.O_DIRECTORY }

		toret = 0
		for xarg in args.split("|"):
			try: toret = toret | tab[xarg]
			except KeyError:
				print xarg
				toret = toret | int(xarg, 16)
		return toret

	def walk_ops(self):

		self.fp.seek(0)

		while True:
			line = self.fp.readline()
			if line.startswith('%dump'):
				break

		if len(line) == 0:
			raise "Wrong_Format"

		while len(line):
			line = self.fp.readline()

			if line.startswith('#') or len(line) < 5:
				continue

			if line.startswith('%'):
				raise StopIteration

			line = line.strip().split(",")

			op = io_op()

			try:	op.tstamp = float(line[0])
			except: continue

			try: op.pid = int(line[1])
			except: pass
			op.optype, args = line[2].split("|", 1)
			args = args.split("|")

			if op.optype == "open":
				op.optype = OP_TYPE_OPEN
				op.fname = args[0]
				op.mode = self.convert_args_string_to_int(args[1])

			elif op.optype == "dup":
				op.optype = OP_TYPE_DUP
				op.fd = int(args[0])

			elif op.optype == "dup2":
				op.optype = OP_TYPE_DUP2
				op.fd = int(args[0])
				op.newfd = int(args[1])

			elif op.optype == "close":
				op.optype = OP_TYPE_CLOSE
				op.fd = int(args[0])

			elif op.optype == "lseek":
				op.optype = OP_TYPE_LSEEK
				op.fd = int(args[0])
				op.block = int(args[1])
				if   args[2] == "SEEK_SET":	op.whence = 0
				elif args[2] == "SEEK_CUR":	op.whence = 1
				elif args[2] == "SEEK_END":	op.whence = 2

			elif op.optype == "read":
				op.optype = OP_TYPE_READ
				op.fd = int(args[0])
				op.size = int(args[2])

			elif op.optype == "write":
				op.optype = OP_TYPE_WRITE
				op.fd = int(args[0])
				op.size = int(args[2])

			elif op.optype == "fcntl":
				op.optype = OP_TYPE_FCNTL
				op.fd = int(args[0])
				op.cmd = args[1]
#				op.arg = args[2]

			if line[3].startswith("0x"):
				op.retcode = int(line[3], 16)
			else:
				op.retcode = int(line[3])

			op.time_elapsed = float(line[4])

			yield op

class io_op:

	pid = None

	optype = None
	tstamp = None
	fd = None
	size = None
	fname = None

	retvalue = None
	time_elapsed = None
	
	def time_finished(self):
		return float(self.tstamp + self.time_elapsed)

	def __str__(self):

		return "%s = %s" % (self.print_call(), self.retcode)

	def print_call(self):

		if self.optype == OP_TYPE_OPEN:
			return "open(%s)" % (self.fname)

		if self.optype == OP_TYPE_READ:
			return "read(%s,%s)" % (self.fd, self.size)

		if self.optype == OP_TYPE_WRITE:
			return "write(%s,%s)" % (self.fd, self.size)

		if self.optype == OP_TYPE_DUP:
			return "dup(%s)" % (self.fd)

		if self.optype == OP_TYPE_CLOSE:
			return "close(%s)" % (self.fd)

		if self.optype == OP_TYPE_DUP2:
			return "dup2(%s,%s)" % (self.fd, self.newfd)

		if self.optype == OP_TYPE_LSEEK:
			return "lseek(%s,%s,%s)" % (self.fd, self.block, self.whence)

		if self.optype == OP_TYPE_FCNTL:
			return "fcntl(%s,%s)" % (self.fd, self.cmd)

		return "[unknown_syscall]"
