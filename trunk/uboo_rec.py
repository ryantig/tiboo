#!/usr/bin/env python

# (C) navid@navid.it

import os
import sys
from stat import *
import pdb
import re
import commands
from optparse import OptionParser, Option
from time import sleep
from tempfile import gettempdir

__cmdParser__ = OptionParser()
__cmdParser__.add_option("-o", "--output", metavar="FILE", \
			dest="dst", type = "string", \
			help="output file")
__cmdParser__.add_option("-c", "--command", metavar="COMMAND", \
			dest="cmd", type = "string", \
			help="command to run")

(__cmdLineOpts__, __cmdLineArgs__) = __cmdParser__.parse_args()

if not __cmdLineOpts__.cmd:
	print
	print """Please specify a command. For example, to analyse a simple dd just run:"""
	print
	print '''\tubuu_rec -c "dd if=/dev/zero of=/tmp/testing123.dat bs=1k count=4"'''
	print
	sys.exit()

if not __cmdLineOpts__.dst:
	__cmdLineOpts__.dst = "appdump.txt"
	print """no output file specified, using "%s".""" % __cmdLineOpts__.dst

fp = open(__cmdLineOpts__.dst, "w")

re_c = re.compile(r"""^(?P<pid>\S+) (?P<timestamp>\S+)\s+(?P<syscall>\S+)\((?P<args>.*)\)\s*=\s*(?P<ret>\S+).*<(?P<time_elapsed>\S+)\>$""")

print

tmppipe = "%s/uboo-%d.pipe" % (gettempdir(), os.getpid())
os.mkfifo(tmppipe)

pid = os.fork()

if not pid:
	sleep(1)
	os.system('''/usr/bin/strace -q -o %s -T -e open,dup,fcntl,dup2,lseek,read,write,close,unlink,unlinkat -ttt -vv -s 0 -f %s''' % (tmppipe, __cmdLineOpts__.cmd) )
	sys.exit()

r = open(tmppipe, "r")

fp.write("%cmdline\n")
fp.write("%s\n" % __cmdLineOpts__.cmd)

fp.write("%dump\n# timestamp,pid,syscall(args),return_value,time_elapsed\n")

fsizes = {}
fdmap = {}

lines = 0
try:
	while True:
		line = r.readline()

		if len(line) == 0:
			break

		if not re_c.match(line):
			print "cannot parse line: %s\n" % line
			fp.write( "# cannot parse line: %s\n" % line)
			continue

		ret = re_c.findall(line)[0]

		if not ret[re_c.groupindex['syscall']-1] in [ "open", "dup", "fcntl", "dup2", "lseek", "read", "write", "close", "unlink", "unlinkat" ]:
			continue

		pid = int(ret[re_c.groupindex['pid']-1])

		syscall = ret[re_c.groupindex['syscall']-1]
		args = ret[re_c.groupindex['args']-1]

		x = []
		for arg in args.split(","):
			x.append( arg.strip(''' "''') )
		args = "|".join(x)

		fp.write( "%s,%s,%s|%s,%s,%s\n" % (ret[re_c.groupindex['timestamp']-1], pid, syscall, args, ret[re_c.groupindex['ret']-1], ret[re_c.groupindex['time_elapsed']-1]) )

		lines += 1

		if syscall == "open":
			fname = args.split("|")[0]

#			if not os.path.isfile(fname):
#				continue

			fdmap[int(ret[re_c.groupindex['ret']-1])] = fname

			try:	fsizes[fname] = os.stat(fname)[ST_SIZE]
			except:	fsizes[fname] = -1

		elif not syscall in "unlink":

			# all other syscalls take "fd" as their first argument
			fd = int(args.split("|")[0])

			if syscall == "close":

				if fdmap.has_key(fd):
					del fdmap[fd]
				else:
					fp.write( "# couldn't resolve fd %s\n" % (fd))

			else:

				if fdmap.has_key(fd):
					continue

				try:	fname = os.readlink("/proc/%d/fd/%d" % (pid, fd))
				except OSError:
					fp.write( "# couldn't resolve fd %d for pid %d\n" % (fd, pid))
					pass

#				if not os.path.isfile(fname):
#					continue

				fdmap[fd] = fname

				try:	fsizes[fname] = os.stat(fname)[ST_SIZE]
				except:	fsizes[fname] = -1

except KeyboardInterrupt:
	print "Keyboard interrupt."
	pass

r.close()
os.unlink(tmppipe)

fp.write("%files\n# filename,size\n")

for fname in fsizes.keys():
	fp.write( "%s|%s\n" % (fname, fsizes[fname]) )

status, output = commands.getstatusoutput("/bin/mount")
fp.write("%mounts\n" + output + "\n")

fp.close()

print
print "%s files used, %d operations captured." % ( len(fsizes), lines )

sys.exit()
