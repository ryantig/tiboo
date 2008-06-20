#!/usr/bin/env python

# (C) navid@navid.it

import os
import sys
from stat import *
import pdb
import re
from optparse import OptionParser, Option

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

os.system('''/usr/bin/strace -q -o /tmp/output.strace -T -e open,dup,fcntl,dup2,lseek,read,write,close,unlink,unlinkat -ttt -vv -s 0 -f %s''' % __cmdLineOpts__.cmd)

r = open("/tmp/output.strace")

fp.write("%cmdline\n")
fp.write("%s\n" % __cmdLineOpts__.cmd)

fp.write("%dump\n# timestamp,pid,syscall(args),return_value,time_elapsed\n")

fsizes = {}

lines = 0
try:
	while True:
		line = r.readline()

		if len(line) == 0:
			break

		if not re_c.match(line):
			print "cannot parse line", line
#			pdb.set_trace()
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

			if not os.path.isfile(fname):
				continue

			try:	fsizes[fname] = os.stat(fname)[ST_SIZE]
			except:	fsizes[fname] = -1

#		else:
#			fd = int(args.split(",")[0])
#			os.system("ls /proc/%s/fd" % pid)

#			fname = os.readlink("/proc/%d/fd/%d" % (pid,fd))
#			if not fsizes.has_key(fname):
#				try:	fsizes[fname] = os.stat(fname)[ST_SIZE]
#				except:	print "WEIRD"

except KeyboardInterrupt:
	print "Keyboard interrupt."
	pass

r.close()

fp.write("%files\n# filename,size\n")

for fname in fsizes.keys():
	fp.write( "%s|%s\n" % (fname, fsizes[fname]) )

fp.close()

print
print "%s files used, %d operations captured." % ( len(fsizes), lines )

sys.exit()
