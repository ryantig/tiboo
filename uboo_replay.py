#!/usr/bin/env python

# (C) navid@navid.it

import os
import sys
import re
from stat import *
from time import time, sleep, clock
import pdb
from optparse import OptionParser, Option

from common import *

SPEED_ASAP = 0
SPEED_NORMAL = 1

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
		if delta > __cmdLineOpts__.min_pause:
#			print "sleeping for %.2fs" % (delta)
			sleep(delta)
		elif delta < -0.1:
			print "[WARNING] lagging behind %.2fs!!!" % delta

		return delta

class fd_table:

	from threading import Lock
	from common import min_avg_max_class

	_lock = Lock()

	table = {}
	vfname_to_name = {}

	read_time_stats  = min_avg_max_class("read_time", unit = "s", base = 1000)
	write_time_stats = min_avg_max_class("write_time", unit = "s", base = 1000)

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
		except IOError: print "cannot seek on vfd %d at byte %d (whence %d)" % (fd, pos, whence)

	def read(self, virtual_fd, bytes):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] read to inexisting vfd %d" % virtual_fd
			return

		try:
			t = time()
			toret = len(os.read(fd, bytes))
			tdiff = time() - t

			if toret > 0:
				print "%.5f" % tdiff
				self.read_time_stats.push(tdiff)

			return toret
		except OSError:
			print "[ERROR} reading %d bytes from vfd %d" % (bytes, virtual_fd)
			return -1

	def write(self, virtual_fd, bytes):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] write to inexisting vfd %d" % virtual_fd
			return

		try:
			t = time()
			toret = os.write(fd, "a" * bytes)
			if toret > 0:
				self.write_time_stats.push( time() - t )
			return toret
		except OSError:
			print "[ERROR} writing %d bytes to vfd %d" % (bytes, virtual_fd)
			return -1

	def dup2(self, virtual_fd, wanted_fd):

		fd = self.get_fd(virtual_fd)

		if not fd:
			print "[ERROR] dup to inexisting vfd %d" % virtual_fd
			return

		newfd = self.get_fd(wanted_fd)

		if newfd:
			self.close(newfd)

		self._lock.acquire()
		self.table[wanted_fd] = os.dup(fd)
		self._lock.release()

		return wanted_fd

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

class io_process:

	from Queue import Queue

	opq = Queue()

	speed = SPEED_ASAP
	speed = SPEED_NORMAL

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

			if self.speed == SPEED_NORMAL:
				time_warp.wait_until_vtime(op.tstamp)

			retcode = None

			if op.optype == OP_TYPE_OPEN:

				retcode = fps.open(virtual_fd = op.retcode, fname = fps.vfname_to_name[op.fname], mode = op.mode)

				if retcode == None:
					continue

				if retcode != op.retcode:
					print "[ERROR] invalid open", retcode, op.retcode

			elif op.optype == OP_TYPE_DUP:
				retcode = fps.dup2(virtual_fd = op.fd, wanted_fd = op.retcode)

			elif op.optype == OP_TYPE_DUP2:
				retcode = fps.dup2(virtual_fd = op.fd, wanted_fd = op.newfd)
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
					os.system("ls -l /proc/self/fd/%d" % fps.get_fd(op.fd) )
					print "[WARNING] bad read: on fd %d expected %d, got %d bytes" % (op.fd, op.retcode, retcode)

			elif op.optype == OP_TYPE_WRITE:
				retcode = fps.write(virtual_fd = op.fd, bytes = op.size)
				if retcode != op.retcode:
					print "[WARNING] bad write: on fd %d expected %d, got %d bytes" % (op.fd, op.retcode, retcode)

			else:
				print "unhandled optype", op.optype

#			print "%s [vpid %s] %s = %s" % (time_warp.time_elapsed(), self.vpid, op.print_call(), retcode)

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

__cmdParser__.add_option("--minpause", metavar="SECONDS", \
			dest="min_pause", type = "int", default=3, \
			help="minimum pauses (in seconds) to consider when replaying I/O")

__cmdParser__.add_option("-t", "--threads", action="store_true", \
                     dest="use_threads", default=False, \
                     help="use threads for different pids")

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

	# always skip /proc entried
	if vfname.startswith("/proc"): continue

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

if os.path.exists("/proc/sys/vm/drop_caches"):

	print
	ans = ""
	while not ans in ["y", "n"]:
		ans = raw_input("Would you like to flush the caches (y/n) ? ")

	if ans == "y":
		if os.getuid() == 0:
			print
			print "Flushing caches..."
			os.system("""/bin/echo 3 > /proc/sys/vm/drop_caches""")
		else:
			print
			print """This operation requires root root permissions, please enter your root password."""
			print
			print "Flushing caches..."
			os.system("""su -c '/bin/echo 3 > /proc/sys/vm/drop_caches'""")

print

time_warp = None

for op in appdump_file.walk_ops():

	if time_warp == None:
		time_warp = time_warp_class(dump_stime = op.tstamp)

	if not __cmdLineOpts__.use_threads:
		op.pid = "main"

	if not vthreads.has_key(op.pid):
		print "spawning new process", op.pid
		vthreads[op.pid] = io_process(vpid = op.pid)
		vthreads[op.pid].start()

	vthreads[op.pid].opq.put(op)

try:
	while True:
		print fps.read_time_stats, fps.write_time_stats
		sleep(1)
		for vt in vthreads:
			if vthreads[vt].opq.qsize() > 0:
				break
		else:
			break

except KeyboardInterrupt:
	print "[INFO] caught keyboard interrupt, exiting."

#os.system('''rm -rf "%s"''' % __cmdLineOpts__.workdir)
