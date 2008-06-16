#!/usr/bin/env python

import re, time, pdb, sys, getopt, datetime, commands, copy
import os
import random

from optparse import OptionParser, Option

OPTIONS = { "rw_breakdown":False }

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

def size_align(value, align):
	spare = value % align
	if spare > 0:
		return value + (align - spare)
	else:
		return value

#	return align * (int(value / align) + 1)
	
def merge_stats(name, v1, v2):

	if not v1.avg():
		toret = copy.copy(v2)
		toret.name = name
		return toret

	toret = copy.copy(v1)
	toret.name = name

	if not v2.avg():
		return toret

	toret.min = min([v1.min, v2.min])
	toret.max = max([v1.max, v2.max])
	toret.sum = sum([v1.sum, v2.sum])
	toret.pushed = sum([v1.pushed, v2.pushed])
	toret.base = v1.base
	toret.unit = v1.unit
	
	return toret

class min_avg_max_class:

	def __init__(self, name, value = None, base = 1000, unit = ""):

		self.name = name
		self.min = None
		self.max = None
		self.sum = 0
		self.pushed = 0
		self.base = base
		self.unit = unit

		if value:
			self.push(value)

	def push(self, value):

		if type(value) == list:
			for x in value:
				self.push(x)
			return

		value = float(value)

		if self.min == None or value < self.min:
			self.min = value

		if self.max == None or value > self.max:
			self.max = value

		self.sum += value
		self.pushed += 1
		
	def avg(self):
		try:	return float(self.sum / self.pushed)
		except:	return None

	def __str__(self):
		return """%s(min/avg/max):%s/%s/%s""" % (self.name, human_value(self.min, self.base, self.unit), human_value(self.avg(), self.base, self.unit), human_value(self.max, self.base, self.unit))
        
class io_class:

	def __init__(self, time, r_or_w, block, disk = None, host = None, length = None, sectors = None, sector_size = None, retcode = None):

		self.time = float(time)
		
		self.disk = disk

		if r_or_w == "r":
			self.read, self.write = True, False
		else:
			self.read, self.write = False, True

		self.block = int(block)
		
		if length:
			self.length = int(length)
			self.sectors = self.length / 512
		elif sectors and sector_size:
			self.length = int(int(sectors) * int(sector_size))
			self.sectors = int(sectors)
			self.sector_size = int(sector_size)
		else:
			raise "Missing_Data"
	
		self.retcode = retcode

	def __str__(self):
		return """%s,%s,%s,%s""" % (self.time,self.write,self.block,self.length)
		
class io_set_class:

	def __init__(self, ios = [], only_disks = None, t_begin = -1, t_end = -1):
    
		self.ios = ios
		self.data_fp = None
		self.t_begin = t_begin
		self.t_end = t_end
		self.only_disks = only_disks
		
	def set_file_source(self, fname):

		self.data_fp = open(fname, "r")
		self.data_fname = fname

	def ios_from_file(self):
	
		while True:

			line = self.data_fp.readline().strip()

			if not line:
				break

			if line[0] == "#" or len(line) == 0:
				continue

			ret = line.split(",")

			io = io_class(time = ret[0], host = ret[1], disk = ret[3], r_or_w = ret[4], block = ret[5], sectors = ret[6], sector_size = ret[7])
			
			if self.only_disks and io.disk not in self.only_disks:
				continue

			if self.t_begin > 0 and io.time < self.t_begin:
				continue

			if self.t_end > 0 and io.time > self.t_end:
				break

			yield io
			
		self.data_fp.seek(0)
		raise StopIteration

	def graph(self):

		from tempfile import mkstemp

		tmp_fd, fname = mkstemp()
		fp = os.fdopen(tmp_fd, 'w+b')

		fp.write('''
set datafile separator ","
set xlabel "UNIX Timestamp"
set xtics auto
set ytics auto
set xtic rotate by -45
#set format x "%d"
#set format y "%d"
#set format x "%Y-%m-%d %H:%M:%S"
#set timefmt "%%s"
#set xdata time
set auto y''')

		fp.write('''
set xrange [1213263960:1213287292]''')

		fp.write('''
# To convert .EPS to .PNG: find tmp -name '*.eps' -exec convert -density 150x150 {} {}.png \;

# LBA access

set title "I/O access - disk seeks" 
set ylabel "LBA (offset)"

set term postscript eps enhanced color size 15,10
set output 'tmp/graph_seeks.eps'

plot	"<awk 'BEGIN {FS=\\",\\"} { iosize=$7*$8/1024 \; if (iosize > 0   && iosize <= 32  ) print $1\\",\\"$6 }' %s" using 1:2 with points lt rgb "#6c971e" pt 7 ps 0.4 title 'size <= 32KiB', \
	"<awk 'BEGIN {FS=\\",\\"} { iosize=$7*$8/1024 \; if (iosize > 32  && iosize <= 128 ) print $1\\",\\"$6 }' %s" using 1:2 with points lt rgb "#6c971e" pt 7 ps 0.5 title 'size <= 128KiB', \
	"<awk 'BEGIN {FS=\\",\\"} { iosize=$7*$8/1024 \; if (iosize > 128 && iosize <= 1024) print $1\\",\\"$6 }' %s" using 1:2 with points lt rgb "#2c971e" pt 7 ps 0.6 title 'size <= 1024KiB', \
	"<awk 'BEGIN {FS=\\",\\"} { iosize=$7*$8/1024 \; if (iosize > 1024                 ) print $1\\",\\"$6 }' %s" using 1:2 with points lt rgb "#095000" pt 7 ps 0.7 title 'size > 1MiB'

# Bandwidth

set title "I/O access - bandwidth" 
set ylabel "KiB/s"

set term postscript eps color size 15,5
set output 'tmp/graph_throughput.eps'

plot "<awk 'BEGIN {FS=\\",\\"; timo=\\"\\"} {x=x+($7 * $8)/1024; if (timo != $1) {print $1\\",\\"x; timo = $1; x = 0} }' %s" with boxes lt 2 title 'bandwidth (KiB/s)'

# IOPS

set title "I/O access - I/O operations per second" 
set ylabel "iops"

set term postscript eps color size 15,5
set output 'tmp/graph_iops.eps'

plot "<awk 'BEGIN {FS=\\",\\"; timo=\\"\\"} {x=x+1; if (timo != $1) {print $1\\",\\"x; timo = $1; x = 0} }' %s" with boxes lt 3 title "I/O operations per second"''' % \
		(self.data_fname, self.data_fname, self.data_fname, self.data_fname, self.data_fname, self.data_fname) )

		fp.close()

		print fname , commands.getstatusoutput("gnuplot %s" % fname)

#		os.unlink(fname)
			
	def text_graph(self):
	
		for sec, io_in_second in self.list_io_in_second(group_secs = 10):
			print sec, (len(io_in_second) / 10) * "+"
			bs = min_avg_max_class("bs", value =  map(lambda x: x.length, io_in_second), unit = "B")
			print sec, int(bs.sum / 1000000) * "*"
			
	def list_io_in_second(self, group_secs = 1):

		io_in_second = []

		for io in self.ios_from_file():

			if len(io_in_second) > 0 and ( int(io.time) > int(io_in_second[0].time) + group_secs - 1 ):
			
				yield int(io_in_second[0].time), io_in_second

				for sec in range(int(io_in_second[0].time) + 1 + group_secs - 1, int(io.time)):
					yield int(sec), []

				io_in_second = [io]

			else:

				io_in_second.append(io)

	def analyse(self):

		first_time = True
		total_iops = min_avg_max_class("total_iops")
		total_bs = min_avg_max_class("total_bs")
		total_random = min_avg_max_class("total_random")
		
		for sec, io_in_second in self.list_io_in_second():

			if first_time == True:
				first_time = sec
			
			# iops, randomness, read/writes nr, r/w bytes, seq read/writes, throughput, service times
			# block access
			
			io_r = filter(lambda x: x.write != True, io_in_second)
			io_w = filter(lambda x: x.write == True, io_in_second)

			iops = len(io_in_second)
			iops_w = len(io_w)
			iops_r = iops - iops_w
				
			bs_r = min_avg_max_class("bs_reads", value =  map(lambda x: x.length, io_r), unit = "b")
			bs_w = min_avg_max_class("bs_writes", value =  map(lambda x: x.length, io_w), unit = "b")
			bs = merge_stats("bs", bs_r, bs_w)

			seq_r, seq_w, random_ops = seq_random_analysis(io_in_second)
			seq = merge_stats("seq", seq_r, seq_w)
			
			if iops > 0:
			
				print """t:%d iops:%d(%d%% reads, %d%% random) %s %s bytes:%s seq_bytes:%s""" % (sec, iops, iops_r*100/iops,  random_ops*100/iops, seq, bs, human_byte_sizes(bs.sum), human_byte_sizes(seq.sum))
				
			else:

				print """t:%d iops:0""" % sec

			total_iops.push(iops)

			try:    total_random.push(random_ops*100/iops)
			except:
					if iops > 0: total_random.push(0)
			
			total_bs = merge_stats("total_bs", bs, total_bs)
			
		if first_time == True:
			print "not enough data was found."
			sys.exit()

		print
		print "Summary:"
		print
		print "\tPeriod analysed: %d seconds" % (sec - first_time)
		print "\tTotal I/O requests: %d" % total_iops.sum
		print "\tAverage IOPS: %s" % human_value(total_iops.avg(), 1000)
		print "\tTotal bytes transferred:", human_byte_sizes(total_bs.sum)
		print "\tAverage throughput: %s/s" % human_byte_sizes(total_bs.sum / ( sec - first_time ) )
		print "\t", total_iops, total_random
		print

	def replay(self, read_only = True, make_writes_as_reads = False, speed = 1, disk_to_disk = {}, asap = False, framedrop = False, offset = True):

		import directio

		if make_writes_as_reads:
			read_only = True

		if framedrop and asap:
			print "notice: can't use framedrop with asap, disabling framedrop."
			framedrop = False

		if offset == True:
			offset = random.randint(1024 * 1024 * 50, 1024 * 1024 * 100)
			print "using random offset of %d" % offset
		elif offset == False:
			offset = 0

		fps = {}

		for io in self.ios_from_file():
        
			if io.disk in fps.keys():
				continue
				
			if io.write and read_only and not make_writes_as_reads: # and os.stat(disk)
				print """Data replay would write to disk %s, but read-only mode is enabled.""" % io.disk
				print """Disable read-only mode or enable "make_writes_as_reads" to convert writes to reads."""
				return False

			if not read_only and not make_write_as_reads and io.write == True:
				op = "w"
			else:
				op = "r"

			op = "r"

			if io.disk in disk_to_disk.keys():
				dev = "/dev/%s" % disk_to_disk[io.disk]
			else:
				dev = "/dev/%s" % io.disk

			print """adding device "%s" (will use %s) in %s mode""" % (io.disk, dev, op)

			try:
				fps[io.disk] = directio.open(dev, directio.O_RDONLY, 0644)
			except IOError:
				print "error: could not open %s" % dev
				return False
				
			if ios.only_disks and len(fps) == len(ios.only_disks):
				break
 
		print "Preliminary checks were successful, beginning test..."
		time_begin = time.time()
		time_first = None
		await = min_avg_max_class("await", base = 1000, unit = "s")
		srv_time = min_avg_max_class("srv_time", base = 1000, unit = "s")
		skipped_frames = 0

		try:

			for io in self.ios_from_file():
		
				if not time_first:
					time_first = io.time

	#			print "doing", io.time, time_first, (time.time() - time_begin)

				if not asap:
					tdiff = (io.time - time_first) / speed - ((time.time() - time_begin))
					if tdiff > 0:
	 #  	             print "sleeping", tdiff, time.time() - time_begin, io.time
						time.sleep(tdiff)
					elif tdiff < -0.02 and framedrop:
						print "warning: skipping frame (lagging %dms)" % abs(tdiff * 1000)
						skipped_frames += 1
						continue

				sector = size_align(io.block + offset, 512)

				if sector != os.lseek(fps[io.disk], sector, 0):
					print "got different sector than asked", sector

				timer = time.time()

				done_bytes = 0

				while done_bytes < io.length:

					do_bytes = size_align(io.length - done_bytes, 512)
					if do_bytes > 4096:
						do_bytes = 512 * 518

					txt = directio.read(fps[io.disk], do_bytes)

					if len(txt) == 0:
						break

					done_bytes += len(txt)

				del txt
				if done_bytes < io.length:
					print "short read/write, sector %d, wanted %d bytes, read %d bytes" % (sector, io.length, done_bytes)

				srv_time.push(time.time() - timer)
				if not asap:
					await.push(time.time() - (time_begin + (io.time - time_first)) )

				if srv_time.pushed % 10 == 0:
					print await, srv_time, "skipped %d%% frames" % (skipped_frames * 100 / srv_time.pushed)

		except KeyboardInterrupt:
			print "Keyboard interrupt caught, terminating."

		for fp in fps.values():
#			fp.close()
			directio.close(fp)
                        
		print srv_time, (skipped_frames * 100 / srv_time.pushed)

def seq_random_analysis(ios):

	seq_r = min_avg_max_class("seq_read_bytes", base = 1024, unit = "B")
	seq_w = min_avg_max_class("seq_write_bytes", base = 1024, unit = "B")
	seek = min_avg_max_class("seek_diff", base = 1024, unit = "B")
	random_seeks = 0
	prev_io = None

	for io in ios:
	
		if not prev_io:
			prev_io = io
			continue
			
		if prev_io.block < io.block and io.block < prev_io.block + prev_io.length:
			seek_diff = 0
		elif prev_io.block < io.block:
			seek_diff = io.block - prev_io.block
		else:
			seek_diff = prev_io.block + prev_io.length - io.block

		if prev_io.write == io.write and seek_diff < 1024: # same kind of operation

			if io.write == True:
				seq_w.push(io.length)
			else:
				seq_r.push(io.length)

		else:
		
			seek.push(seek_diff)
			random_seeks += 1

		prev_io = io
		
	if random_seeks > 0:
		random_seeks += 1

	return seq_r, seq_w, random_seeks

class OptionParser_extended(OptionParser):
    def print_help(self):
        OptionParser.print_help(self)

        print "Some examples:"
        print
        print " draw a text-based graph showing activity (iops and throughput) per second:"
        print 
        print "   # ioanalyse -g -s dump.csv"
        print 
        print """ analyse an I/O dump considering "sdb" only, stop at timestamp 1211881488,\n write output to screen and to file (results.txt):"""
        print 
        print "   # ioanalyse -s dump.csv -e 1211881488 --only-disk sdb | tee results.txt"
        print 

class Navid_Option (Option):
    """Allow to specify comma delimited list of plugins"""
    ACTIONS = Option.ACTIONS + ("extend",)
    STORE_ACTIONS = Option.STORE_ACTIONS + ("extend",)
    TYPED_ACTIONS = Option.TYPED_ACTIONS + ("extend",)

    def take_action(self, action, dest, opt, value, values, parser):
        if action == "extend":
            try: lvalue = value.split(",")
            except: pass
            else: values.ensure_value(dest, []).extend(lvalue)
        else:
            Option.take_action(self, action, dest, opt, value, values, parser)

__cmdParser__ = OptionParser_extended(option_class=Navid_Option)
__cmdParser__.add_option(	"-s", "--src", metavar="FILE", \
							dest="src", type = "string", \
                     		help="data source file or device")
__cmdParser__.add_option("-a", "--analyse", action="store_true", \
                     dest="do_analyse", default=False, \
                     help="analyse disk access and provide statistics (default)")
__cmdParser__.add_option("-g", "--graph", action="store_true", \
                     dest="do_graph", default=False, \
                     help="analyse disk access and provide graph")                     
__cmdParser__.add_option("-t", "--textgraph", action="store_true", \
                     dest="do_text_graph", default=False, \
                     help="analyse disk access and provide graph")
__cmdParser__.add_option(	"-b", metavar="TSTAMP", \
		     dest="t_begin", type = "int", default=-1, \
                     help="begin at timestamp")
__cmdParser__.add_option(	"-e", metavar="TSTAMP", \
		     dest="t_end", type = "int", default=-1, \
                     help="end parsing at timestamp")
__cmdParser__.add_option("-r", "--replay", action="store_true", \
                     dest="do_replay", default=False, \
                     help="replay disk access")
__cmdParser__.add_option(	"--only-disk", metavar="DEVICE", \
		     dest="only_disks", type = "string", action = "extend", default = [], \
                     help="only consider DEVICE")
__cmdParser__.add_option(	"--disk-to-disk", metavar="DEVICE1,DEVICE2", \
		     dest="disk_to_disk", type = "string", action = "extend", default = [], \
                     help="replace occurrences of DEVICE1 in file with DEVICE2")

(__cmdLineOpts__, __cmdLineArgs__) = __cmdParser__.parse_args()

if not __cmdLineOpts__.src:
	__cmdParser__.print_help()
	sys.exit()

ios =  io_set_class(only_disks = __cmdLineOpts__.only_disks, t_begin = __cmdLineOpts__.t_begin, t_end = __cmdLineOpts__.t_end)

ios.set_file_source(__cmdLineOpts__.src)
	
print
print "tiboo (c) navid@navid.it"
print
    
if not ( __cmdLineOpts__.do_replay or __cmdLineOpts__.do_graph or  __cmdLineOpts__.do_text_graph):
	__cmdLineOpts__.do_analyse = True

if __cmdLineOpts__.do_analyse:

	if __cmdLineOpts__.disk_to_disk:
		print "error: --disk-to-disk can only be used when replaying data."
		sys.exit()
		
	ios.analyse()

if __cmdLineOpts__.do_graph:
	ios.graph()

if __cmdLineOpts__.do_text_graph:
	ios.text_graph()
	
if __cmdLineOpts__.disk_to_disk:
	tmp = {}
	for one in __cmdLineOpts__.disk_to_disk:
		one = one.split(":", 2)
		tmp[one[0]] = one[1]
	__cmdLineOpts__.disk_to_disk = tmp
	del tmp
else:
	__cmdLineOpts__.disk_to_disk = {}

if __cmdLineOpts__.do_replay:
	ios.replay(make_writes_as_reads = True, speed = 1, disk_to_disk = __cmdLineOpts__.disk_to_disk)
