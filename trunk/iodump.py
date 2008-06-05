#!/usr/bin/env python

# (C) navid@navid.it

import re, time, pdb, sys, getopt, datetime, commands
from optparse import OptionParser, Option

# scsi_logging_level.sh -c -H 3
# sysctl dev.scsi.logging_level=56623104

def usage():
   print "iodump"

re_c = re.compile(r"""^\<[0-9]>sd (?P<scsi_id>\S+): \[(?P<disk>\S+)\] sd_init_command: block=(?P<block>[0-9]+), count=(?P<count>[0-9]+)\n""" +
"""\<[0-9]>sd \S+: \[\S+\] block=[0-9]+\n""" +
"""\<[0-9]>sd \S+: \[\S+\] (?P<read_or_write>.)\S+ [0-9]+/[0-9]+ (?P<sector_size>[0-9]+) byte blocks\.\n""" + "" +
"""\<[0-9]>sd \S+: \[\S+\] Result: hostbyte=(?P<host_byte>\S+) driverbyte=(?P<driver_byte>\S+)$""",
re.MULTILINE)

re_c = re.compile(r"""^\<[0-9]>sd_(?P<scsi_id>init)_command: disk=(?P<disk>\S+), block=(?P<block>[0-9]+), count=(?P<count>[0-9]+)\n""" +
"""\<[0-9]>\S+ : block=[0-9]+\n""" +
"""\<[0-9]>\S+ : (?P<read_or_write>.)\S+ [0-9]+/[0-9]+ (?P<sector_size>[0-9]+) byte blocks\.\n""" + "" +
"""\<[0-9]>sd_rw_intr: \S+: res=0x0\n""" + "" +
"""\<[0-9]>[0-9]+ sectors total, [0-9]+ bytes done\.$""",
re.MULTILINE)

re_c = re.compile(r"""^sd_(?P<scsi_id>init)_command: disk=(?P<disk>\S+), block=(?P<block>[0-9]+), count=(?P<count>[0-9]+)\n""" +
"""\S+ : block=[0-9]+\n""" +
"""\S+ : (?P<read_or_write>.)\S+ [0-9]+/[0-9]+ (?P<sector_size>[0-9]+) byte blocks\.\n""" + "" +
"""sd_rw_intr: \S+: res=0x0\n""" + "" +
"""[0-9]+ sectors total, [0-9]+ bytes done\.$""",
re.MULTILINE)

re_c = re.compile(r"""^sd_(?P<scsi_id>init)_command: disk=(?P<disk>\S+), block=(?P<block>[0-9]+), count=(?P<count>[0-9]+)\r*\n""" +
"""\S+ : block=[0-9]+\r*\n""" +
"""\S+ : (?P<read_or_write>.)\S+ [0-9]+/[0-9]+ (?P<sector_size>[0-9]+) byte blocks\.\r*\n$""",
re.MULTILINE)

status, hostname = commands.getstatusoutput("uname -n")

#sd_init_command: disk=sda, block=50343259, count=8
#sda : block=50343259
#sda : writing 8/8 512 byte blocks.
#sd_rw_intr: sda: res=0x0
#376 sectors total, 192512 bytes done.

# Apr 11 18:44:01 localhost kernel: use_sg is 2
# Apr 11 18:44:01 localhost kernel: sd 2:0:0:0: [sda] sd_init_command: block=1355910, count=8
# Apr 11 18:44:01 localhost kernel: sd 2:0:0:0: [sda] block=1355910
# Apr 11 18:44:01 localhost kernel: sd 2:0:0:0: [sda] writing 8/8 512 byte blocks.
# Apr 11 18:44:01 localhost kernel: sd 2:0:0:0: [sda] Result: hostbyte=DID_OK driverbyte=DRIVER_OK,SUGGEST_OK
# Apr 11 18:44:01 localhost kernel: 8 sectors total, 4096 bytes done.

def is_syslogd_running():
	return commands.getstatusoutput("/usr/sbin/lsof -n /var/log/messages")[0] == 0

def sysctl_set_logging(level):
	return commands.getstatusoutput("/sbin/sysctl dev.scsi.logging_level=%d" % int(level) )[0]


__cmdParser__ = OptionParser()
__cmdParser__.add_option(	"-f", "--force", action="store_true", \
							dest="do_force", default=False, \
                     		help="don't check prerequisites")
__cmdParser__.add_option(	"-s", "--src", metavar="FILE", \
							dest="src", type = "string", default="/proc/kmsg", \
                     		help="data source file or device")
__cmdParser__.add_option(	"-o", "--output", metavar="FILE", \
							dest="output", type = "string", default=None, \
                     		help="output file")

(__cmdLineOpts__, __cmdLineArgs__) = __cmdParser__.parse_args()
print __cmdLineOpts__

Opts = {"src":"/proc/kmsg", "from_kmsg":True}
	
if not __cmdLineOpts__.src in [ "/proc/kmsg" ]:
	Opts["from_kmsg"] = False

try:	fp = open(__cmdLineOpts__.src, "r")
except IOError:
	print "error: could not access %s for reading" % __cmdLineOpts__.src
	sys.exit(2)

if is_syslogd_running():
	print "syslogd might be currently running, please stop the process before running this script or you might risk to fill your disk."
	sys.exit(1)
	
if Opts["from_kmsg"]:

	status, old_logging_level = commands.getstatusoutput("/sbin/sysctl -n dev.scsi.logging_level")

	if status != 0:
		print "error getting current logging level.", old_logging_level
		sys.exit(1)

	if sysctl_set_logging(56623104):
		print "error setting logging level"
		sys.exit(1)

first_time = None
line = ""

print "# timestamp,hostname,scsi_id,disk,operation,block,sectors,sector_size"
outbuf = "#timestamp,hostname,scsi_id,disk,operation,block,sectors,sector_size\n"

while True:

	try:
		line += fp.readline()
	except KeyboardInterrupt:
		print "caught keyboard interrupt."
		break

	if not line:
		break

#	print "GOTCHA"

	matched = False
	
	for ret in re_c.findall(line):

		matched = True

		ret = [ xval for xval in ret ]

		ret.insert(0, hostname)
		ret.insert(0, time.time())

		outbuf += "%d,%s,%s,%s,%s,%s,%s,%s\n" % (ret[0], ret[1], ret[2], ret[3], ret[6], ret[4], ret[5], ret[7])

		print "%d,%s,%s,%s,%s,%s,%s,%s" % (ret[0], ret[1], ret[2], ret[3], ret[6], ret[4], ret[5], ret[7])

	if (not matched and line.find("sd_init_command") == -1) or matched:
		line = ""


if Opts["from_kmsg"]:

		print("setting logging level back to old value (%s)." % old_logging_level)

		if sysctl_set_logging(old_logging_level) != 0:
			print("error setting logging level.")
			sys.exit(1)

if __cmdLineOpts__.output:

	fp = open(__cmdLineOpts__.output, "w")	
	print '''writing dump to "%s".''' % __cmdLineOpts__.output
	fp.write(outbuf)
	fp.close()

sys.exit(0)
