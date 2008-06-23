#!/usr/bin/env python


# (C) navid@navid.it

import os
import sys
import re
from stat import *
from time import time, sleep
import pdb
from optparse import OptionParser, Option

OP_TYPE_OPEN  = 10
OP_TYPE_DUP   = 12
OP_TYPE_DUP2  = 14
OP_TYPE_FCNTL = 15
OP_TYPE_LSEEK = 16
OP_TYPE_READ  = 18
OP_TYPE_WRITE = 20
OP_TYPE_CLOSE = 22

class time_warp_class:

	def __init__(self, dump_stime, real_stime = None):

		self.dump_stime = dump_stime

		if not real_stime:
			self.real_stime = time() + 2
		else:
			self.real_stime = real_stime

		self._delta_dump_real_time = self.real_stime - self.dump_stime

	def time_elapsed(self):

		return time() - self.real_stime

	def vtime(self):

		return self.dump_stime + self.time_elapsed()

	def wait_until_vtime(self, vtime):
		delta = vtime - self.vtime()
		if delta > 0:
			if delta > 1:
				print "sleeping for %.2fs" % (delta)
			sleep(delta)
		elif delta < -0.1:
			print "[WARNING] lagging behind %.2fs!!!" % delta

		return delta

class fd_table:

	from threading import Lock

	_lock = Lock()

	table = {}
	vfname_to_name = {}

	def open(self, virtual_fd, fname, mode):

		virtual_fd = int(virtual_fd)

		self._lock.acquire()
		self.table[virtual_fd] = os.open(fname, mode)
		self._lock.release()

		return virtual_fd

	def is_vfd_valid(self, vfd):
		try:	return self.get_fd(vfd) not in [ None, False ]
		except: return False

	def get_fd(self, virtual_fd):

		virtual_fd = int(virtual_fd)

		try:	return self.table[virtual_fd]
		except KeyError:
			return False

		try: return self.table[virtual_fd].fileno()
		except KeyError: return False

	def lseek(self, virtual_fd, pos, whence):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] lseek to inexisting vfd %d" % virtual_fd
			return

		try: return os.lseek(fd, pos, whence)
		except IOError: print "cannot seek there"
		except OSError: print "cannot seek there", self.table

	def read(self, virtual_fd, bytes):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] read to inexisting vfd %d" % virtual_fd
			return

		try: return len(os.read(fd, bytes))
		except OSError:
			print "[ERROR} reading %d bytes from vfd %d" % (bytes, virtual_fd)
			return -1

	def write(self, virtual_fd, bytes):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] write to inexisting vfd %d" % virtual_fd
			return

		try: return os.write(fd, "a" * bytes)
		except OSError:
			print "[ERROR} writing %d bytes to vfd %d" % (bytes, virtual_fd)
			print os.lseek(fd, 0, 1), os.read(fd, 4)
#			sys.exit()
			return -1

	def dup2(self, virtual_fd, newfd):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] dup to inexisting vfd %d" % virtual_fd
			return

		newfd = self.get_fd(newfd)

		if newfd:
			self.close(newfd)

		self._lock.acquire()
		self.table[newfd] = os.dup(fd)
		self._lock.release()

		return newfd

	def close(self, virtual_fd):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] close to inexisting vfd %d" % virtual_fd
			return

		os.close(fd)

		self._lock.acquire()
		del self.table[virtual_fd]
		self._lock.release()

		return 0

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
			raise "EOF"

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

	def __str__(self):

		return "%s = %s" % (self.print_call(), op.retcode)

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


class io_process:

	from Queue import Queue

	opq = Queue()

	def __init__(self, vpid):
		if vpid != None:
			self.vpid = vpid
		else:
			self.vpid = "main"

	def start(self):
		from threading import Thread

		self._thread = Thread(target=self.work_queue)
		self._thread.setDaemon(True)
		self._thread.start()

	def work_queue(self):

		sleep(1)

		while True:

			op = self.opq.get()

			if op.optype != OP_TYPE_OPEN and not fps.is_vfd_valid(op.fd):
				continue

			if op.optype == OP_TYPE_OPEN and not fps.vfname_to_name.has_key(op.fname):
				continue

			delta = time_warp.wait_until_vtime(op.tstamp)

			retcode = None

			if op.optype == OP_TYPE_OPEN:

				retcode = fps.open(virtual_fd = op.retcode, fname = fps.vfname_to_name[op.fname], mode = op.mode)

				if retcode == None:
					continue

				if retcode != op.retcode:
					print "[ERROR] invalid open", retcode, op.retcode

			elif op.optype == OP_TYPE_DUP:
				retcode = fps.dup2(virtual_fd = op.fd, newfd = op.retcode)

			elif op.optype == OP_TYPE_DUP2:
				retcode = fps.dup2(virtual_fd = op.fd, newfd = op.newfd)
				if retcode != op.retcode:
					print "[ERROR] invalid dup2", retcode, op.retcode

			elif op.optype == OP_TYPE_LSEEK:
				retcode = fps.lseek(virtual_fd = op.fd, pos = op.block, whence = op.whence)
				if retcode != op.retcode:
					print "[ERROR] invalid seek", retcode, op.retcode

			elif op.optype == OP_TYPE_CLOSE:
				retcode = fps.close(virtual_fd = op.fd)

			elif op.optype == OP_TYPE_READ:
				retcode = fps.read(virtual_fd = op.fd, bytes = op.size)
				if retcode != op.retcode:
					print "[WARNING] short read!", retcode, op.retcode

			elif op.optype == OP_TYPE_WRITE:
				retcode = fps.write(virtual_fd = op.fd, bytes = op.size)
				if retcode != op.retcode:
					print "[WARNING] short write!", retcode, op.retcode

			else:
				print "unhandled optype", op.optype

			print "%s [vpid %s] %s = %s" % (time_warp.time_elapsed(), self.vpid, op.print_call(), retcode)

__cmdParser__ = OptionParser()

__cmdParser__.add_option("-i", "--input", metavar="FILE", \
			dest="src", type = "string", \
			help="input file")

__cmdParser__.add_option("-w", "--workdir", metavar="DIR", \
			dest="workdir", type = "string", \
			help="working directory")

__cmdParser__.add_option("-p", "--pattern", metavar="PATTERN", \
			dest="pattern", type = "string", \
			help="replay I/O for files that match this mattern (comma separated list allowed)")

(__cmdLineOpts__, __cmdLineArgs__) = __cmdParser__.parse_args()

if not __cmdLineOpts__.src:
	print """Please specify an input file (created using appdump)."""
	sys.exit()

appdump_file = appdump_file(__cmdLineOpts__.src)

if not __cmdLineOpts__.pattern:
	print
	print """Please specify a comma-separated list of file names to replay:"""
	print
	files = appdump_file.file_and_sizes.keys()
	files.sort()
	for vfname in files:
		print """ - %s""" % vfname
	print
	sys.exit()
else:
	__cmdLineOpts__.pattern = __cmdLineOpts__.pattern.split(",")

from tempfile import mkdtemp

if not __cmdLineOpts__.workdir:
	__cmdLineOpts__.workdir = mkdtemp( prefix = "appreplay-" )
	print """no working directory specified, using "%s".""" % __cmdLineOpts__.workdir

fps = fd_table()

vthreads = {}

print "Creating temporary files..."

def mangle_filename(exe):
	mangledname = re.sub(r"^/(usr/|)(bin|sbin)/", "", exe)
	mangledname = re.sub(r"[^\w\-\.\/]+", "_", mangledname)
	mangledname = re.sub(r"/", ".", mangledname).strip(" ._-")[0:64]
	return mangledname

inc = 0
for vfname in appdump_file.file_and_sizes:
#	if not vfname.startswith("/tmp"): continue
	for onepat in __cmdLineOpts__.pattern:
		if vfname.startswith(onepat): break
	else:
		continue

	fps.vfname_to_name[vfname] = "%s/%d_%s" % (__cmdLineOpts__.workdir, inc, mangle_filename(vfname))
	if os.path.exists(fps.vfname_to_name[vfname]):
		print "[ERROR] file %s already exists." % fps.vfname_to_name[vfname]
		sys.exit(1)
	fp = open(fps.vfname_to_name[vfname], "w")
	towrite = appdump_file.file_and_sizes[vfname]
	while towrite > 0:
		fp.write("a" * min([towrite, 4096]))
		towrite-=4096
	fp.close()
	print " - %s -> %s (%d bytes)" % (vfname, fps.vfname_to_name[vfname], appdump_file.file_and_sizes[vfname])
	inc += 1

print "Done."

time_warp = None

for op in appdump_file.walk_ops():

	if time_warp == None:
		time_warp = time_warp_class(dump_stime = op.tstamp)

	op.pid = "main"

	if not vthreads.has_key(op.pid):
		print "spawning new process", op.pid
		vthreads[op.pid] = io_process(vpid = op.pid)
		vthreads[op.pid].start()

	vthreads[op.pid].opq.put(op)

from time import sleep

try:	sleep(3600)
except KeyboardInterrupt:
	print "[INFO] caught keyboard interrupt, exiting."

os.system('''rm -rf "%s"''' % __cmdLineOpts__.workdir)
