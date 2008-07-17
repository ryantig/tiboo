#!/usr/bin/env python

# (C) navid@navid.it

import os
import sys
import re
from stat import *
from time import time, sleep, clock
from optparse import OptionParser, Option

from common import *

__cmdParser__ = OptionParser()

__cmdParser__.add_option("-i", metavar="FILE", \
			dest="src", type = "string", \
			help="input file")

__cmdParser__.add_option("-o", metavar="OUTNAME", \
			dest="outname", type = "string", \
			help="base name for output files")

__cmdParser__.add_option("-n", metavar="FNAME", \
			dest="fname", type = "string", \
			help="filename to watch")

__cmdParser__.add_option("-m", metavar="SECONDS", \
			dest="min_pause", type = "int", default=0, \
			help="skip delays between I/O below this value")

(__cmdLineOpts__, __cmdLineArgs__) = __cmdParser__.parse_args()

if not __cmdLineOpts__.src:
	print """Please specify an input file (created using appdump)."""
	sys.exit()

appdump_file = appdump_file(__cmdLineOpts__.src)

if not __cmdLineOpts__.fname:
	print
	print """Please specify a comma-separated list of file names to replay:"""
	print
	sys.exit()

if not __cmdLineOpts__.outname:
	__cmdLineOpts__.outname = os.path.basename(__cmdLineOpts__.fname).split('.', 1)[0]

fp_r = open("%s_read_telemetry.txt" % __cmdLineOpts__.outname, "w")
fp_w = open("%s_write_telemetry.txt" % __cmdLineOpts__.outname, "w")

fds = []
pos = 0
r_time_old = None
w_time_old = None

for op in appdump_file.walk_ops():

	if op.optype != OP_TYPE_OPEN and not op.fd in fds:

		continue

	if op.optype == OP_TYPE_OPEN:

		if op.fname == __cmdLineOpts__.fname:
			fds.append(op.retcode)
		else:
			continue

	elif op.optype in [ OP_TYPE_DUP, OP_TYPE_DUP2 ]:
	
		fds.append(op.retcode)
   
	elif op.optype == OP_TYPE_LSEEK:

		if   op.whence == 0:  pos = op.block
		elif op.whence == 1:  pos = pos + op.block
		elif op.whence == 2:  raise "Not_Implemented"

	elif op.optype == OP_TYPE_CLOSE:

		del fds[fds.index(op.fd)]

	elif op.optype == OP_TYPE_READ:

		if not r_time_old:	delay = 0
		else:			delay = (op.tstamp - r_time_old) * 1000

		print "read %d bytes at position %d after %d msecs" % (op.size, pos, delay)
		fp_r.write("%d %d %d\n" % (pos, op.size, delay))

		pos += op.retcode
		r_time_old = op.time_finished()

	elif op.optype == OP_TYPE_WRITE:

		if not w_time_old:	delay = 0
		else:			delay = (op.tstamp - w_time_old) * 1000

		delay = 5000

		print "write %d bytes at position %d after %d msecs" % (op.size, pos, delay)
		fp_w.write("%d %d %d\n" % (pos, op.size, delay))

		pos += op.retcode
		w_time_old = op.time_finished()

	else:
	
		print "Not implemented", op
		raise "Not_Implemented"
		
fp_r.close()
fp_w.close()

#print """iozone usage example: iozone -r %s -w %s -w /tmp/sasa"""
