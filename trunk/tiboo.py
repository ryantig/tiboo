#!/usr/bin/env python

import re, time, pdb, sys, getopt, datetime, commands, copy
import os
import random

from optparse import OptionParser, Option

from common import *

OPTIONS = { "rw_breakdown":False }

def k_get(array, key, alt_ret):
	try:		 return array[key]
	except KeyError: return alt_ret

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

class io_class:

	def __init__(self, time, r_or_w, sector, disk = None, host = None, length = None, sectors = None, sector_size = None, retcode = None):

		self.time = float(time)
		
		self.disk = disk

		if r_or_w == "r":
			self.read, self.write = True, False
		else:
			self.read, self.write = False, True

		self.sector = int(sector)

		self.block = int(sector) * 512

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

			io = io_class(time = ret[0], host = ret[1], disk = ret[3], r_or_w = ret[4], sector = ret[5], sectors = ret[6], sector_size = ret[7])
			
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

		only_disks = ",".join(__cmdLineOpts__.only_disks)

#plot "<awk 'BEGIN {FS=\\",\\"} { if (\\"%s\\"!=\\"\\" && \\"%s\\"!=$4) next; ios+=1; tt+=$7*$8/1024; ret[$7*$8/1024]+=1 } END { for (x in ret) print x\\",\\"ret[x]*x/tt*100\\",\\"ret[x]/ios*100}' %s | sort -g -t ," using 2:xtic(1) with histograms title 'Data transferred (%%)', '' using 3 with histograms title 'Requests (%%)'


		fp.write('''
set datafile separator ","
set ytics auto
set xtic rotate by -45
set auto y

set term postscript eps enhanced color size 15,10 font 20

# To convert .EPS to .PNG: find tmp -name '*.eps' -exec convert -transparent white -density 150x150 {} data/logo.png -gravity center -composite -format png {}.png \;

set title "I/O size (data tranferred for size)" font ",40"
set xlabel "Request size (KiB)"
set ylabel "Percentage"

#set style data histogram
set style histogram clustered gap 2 title offset character 0, 0, 0
set style fill solid border -1

set xtics font ",14"
set xrange [0:]
set yrange [0:]

set output '%s_iosizes.eps'

plot "<awk 'BEGIN {FS=\\",\\"} { if (\\"%s\\"!=\\"\\" && \\"%s\\"!=$4) next; ios+=1; iosize=$7*$8/1024; sizes[iosize]=1; if ($5==\\"r\\") r_ret[iosize]+=1; else w_ret[iosize]+=1; } END { for (x in sizes) print x\\",\\"r_ret[x]/ios*100\\",\\"w_ret[x]/ios*100}' %s | sort -g -t ," using 2:xtic(1) with histograms title 'Reads (%%)', '' using 3 with histograms title 'Writes (%%)'

# All the following use X-AXIS as time

set xrange [*:*] noreverse nowriteback
set yrange [*:*] noreverse nowriteback
set xtics auto font ""
set mxtics default
set style fill solid noborder
#set format y "%%d"
set format x "%%Y-%%m-%%d\\n\\n%%H:%%M:%%S"
set timefmt "%%s"
set xdata time
unset xlabel
#set xrange [1213275298:1213275518]

# LBA access

set title "I/O access - disk seeks" 
set ylabel "LBA (offset)"

set output '%s_seeks.eps'

plot	"<awk 'BEGIN {FS=\\",\\"} { if (\\"%s\\"!=\\"\\" && \\"%s\\"!=$4) next; ps=$7*$8/1024/150; if ($5 == \\"r\\") { w_iosize=0 \; r_iosize=ps } else { r_iosize=0 \; w_iosize=ps } print $1\\",\\"$6\\",\\"r_iosize\\",\\"w_iosize }' %s" using 1:2:3 with points lt rgb "#6c971e" pt 7 ps variable title 'reads', \
	"" using 1:2:4 with points lt rgb "#0048ff" pt 7 ps variable title 'writes'

# Bandwidth

set title "I/O access - bandwidth" 
set ylabel "KiB/s"

set output '%s_throughput.eps'

plot "<awk 'BEGIN {FS=\\",\\"} { if (\\"%s\\"!=\\"\\" && \\"%s\\"!=$4) next; lineout[int($1)] += $7*$8/1024 } END { \\
step=60; p_xtime=0; \\
j = 1; for (i in lineout) { ind[j] = i; j++ } n = asort(ind); for (i = 1; i <= n; i++) { xtime = ind[i]; \\
if (p_xtime==0 || xtime >= p_xtime + step) { \\
 if (p_xtime!=0) { \\
  print p_xtime\\",\\"int(p_sum/step); \\
 } \\
 p_sum = lineout[xtime]; p_xtime = xtime; \\
} else { p_sum+=lineout[xtime] } } }' %s" using 1:2 with boxes lt 2 title 'bandwidth (KiB/s)'

# IOPS

set title "I/O access - I/O operations per second" 
set ylabel "iops"

set output '%s_iops.eps'

plot "<awk 'BEGIN {FS=\\",\\"} { if (\\"%s\\"!=\\"\\" && \\"%s\\"!=$4) next; lineout[int($1)] += 1 } END { \\
step=1; p_xtime=0; \\
j = 1; for (i in lineout) { ind[j] = i; j++ } n = asort(ind); for (i = 1; i <= n; i++) { xtime = ind[i]; \\
if (p_xtime==0 || xtime >= p_xtime + step) { \\
 if (p_xtime!=0) { \\
  print p_xtime\\",\\"int(p_sum/step); \\
 } \\
 p_sum = lineout[xtime]; p_xtime = xtime; \\
} else { p_sum+=lineout[xtime] } } }' %s" using 1:2 with boxes lt 3 title "I/O operations per second"



''' % 		(__cmdLineOpts__.outname, only_disks, only_disks, self.data_fname, __cmdLineOpts__.outname, only_disks, only_disks, self.data_fname, __cmdLineOpts__.outname, only_disks, only_disks, self.data_fname, __cmdLineOpts__.outname, only_disks, only_disks, self.data_fname) )

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

		fp_g_iops = open("/tmp/g_iops.dat", "w")
		fp_g_bwidth = open("/tmp/g_bwidth.dat", "w")

		buf_iops_break = {}
		buf_iosize_break_r = {}
		buf_iosize_break_w = {}
		buf_seek_break_r = {}
		buf_seek_break_w = {}

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
			
				print """t:%d iops:%d(%d%% reads, %d%% random) %s %s r_bytes:%s w_bytes:%s seq_bytes:%s""" % (sec, iops, iops_r*100/iops,  random_ops*100/iops, seq, bs, human_byte_sizes(bs_r.sum), human_byte_sizes(bs_w.sum), human_byte_sizes(seq.sum))
				
			else:

				print """t:%d iops:0""" % sec

			total_iops.push(iops)

			try:    total_random.push(random_ops*100/iops)
			except:
				if iops > 0: total_random.push(0)
			
			total_bs = merge_stats("total_bs", bs, total_bs)

			# graphing stuff

			fp_g_iops.write("%d %d %d\n" % (sec, iops_r, iops_w))

			fp_g_bwidth.write("%d %d %d\n" % (sec, bs_r.sum / 1024, bs_w.sum / 1024))

			if iops > 0:
				try:		 buf_iops_break[iops]+=1
				except KeyError: buf_iops_break[iops]=1

			for io in io_in_second:

				if io.read:

					if not buf_iosize_break_r.has_key(io.length):
						buf_iosize_break_r[io.length / 1024] = 0

					if not buf_seek_break_r.has_key(io.block):
						buf_seek_break_r[io.block] = 0

					buf_iosize_break_r[io.length / 1024]+=1
					buf_seek_break_r[io.block]+=io.length

				else:
					try:		 buf_iosize_break_w[io.length / 1024]+=1
					except KeyError: buf_iosize_break_w[io.length / 1024]=1

					try:		 buf_seek_break_w[io.block]+=io.length
					except KeyError: buf_seek_break_w[io.block]=io.length


		# close temp files

		fp_g_iops.close()
		fp_g_bwidth.close()
			
		if first_time == True:
			print "not enough data was found."
			sys.exit()

		# finish graphs

		fp_g_iops_break = open("/tmp/g_iops_break.dat", "w")

		if len(buf_iops_break) > 100:
			xfilter = buf_iops_break.values()
			xfilter.sort()
			xfilter = xfilter[-100] # we won't graph values less than this to keep top 50 common iops
		else:
			xfilter = None

		for iops in buf_iops_break:
			if xfilter and buf_iops_break[iops] < xfilter: #buf_iops_break[iops] * 100 < total_iops.sum:
				# skip unsignificant iops stats (less than 1%)
				continue

			fp_g_iops_break.write( "%d %d\n" % (iops, buf_iops_break[iops]) )

		fp_g_iops_break.close()
		del buf_iops_break

		fp_g_iosize_break = open("/tmp/g_iosize_break.dat", "w")

		iosizes = buf_iosize_break_r.keys()
		iosizes.extend(buf_iosize_break_w.keys())
		iosizes = unique(iosizes)
		iosizes.sort()

		for ioz in iosizes:
			rval = k_get(buf_iosize_break_r, ioz, 0) * 100 / total_iops.sum
			wval = k_get(buf_iosize_break_w, ioz, 0) * 100 / total_iops.sum

			if rval == 0 and wval == 0:
				pdb.set_trace()
				continue

			fp_g_iosize_break.write("%d %d %d\n" % (ioz, rval, wval) )

		fp_g_iosize_break.close()
		del buf_iosize_break_r, buf_iosize_break_w, iosizes

		# generate gnuplot file

		from tempfile import mkstemp

		tmp_fd, fname = mkstemp()
		fp = os.fdopen(tmp_fd, 'w+b')

		only_disks = ",".join(__cmdLineOpts__.only_disks)

		fp.write('''
set ytics auto
set xtic rotate by -45
set auto y

set term postscript eps enhanced color size 15,10 font 20

# To convert .EPS to .PNG: find tmp -name '*.eps' -exec convert -transparent white -density 150x150 {} data/logo.png -gravity center -composite -format png {}.png \;

# IOSZE breakdown

set title "I/O size (data tranferred for size)" font ",40"
set xlabel "Request size (KiB)"
set ylabel "Percentage"

set style histogram clustered gap 2 title offset character 0, 0, 0
set style fill solid border -1

set xtics font ",14"
set xrange [0:]
set yrange [0:]

set output "''' + __cmdLineOpts__.outname + '''_iosizes_break.eps"

plot "''' + fp_g_iosize_break.name + '''" using 2:xtic(1) with histograms title 'Reads (%)', '' using 3 with histograms title 'Writes (%)'

# IOPS breakdown

set title "IOPS breakdown (top 100)" font ",40"
set xlabel "IOPS"
set ylabel "Occurrences"

set output "''' + __cmdLineOpts__.outname + '''_iops_break.eps"

plot "''' + fp_g_iops_break.name + '''" using 2:xtic(1) with boxes title 'Reads (%)'

# All the following use X-AXIS as time

set xrange [*:*] noreverse nowriteback
set yrange [*:*] noreverse nowriteback
set xtics auto font ""
set mxtics default
set style fill solid noborder
#set format y "%d"
set format x "%Y-%m-%d\\n\\n%H:%M:%S"
set timefmt "%s"
set xdata time
unset xlabel
#set xrange [1213275298:1213275518]

# LBA access

set title "I/O access - disk seeks" 
set ylabel "LBA (offset)"

set output "''' + __cmdLineOpts__.outname + '''_seeks.eps"
#set datafile separator ","

#plot	"<awk 'BEGIN {FS=\\",\\"} { if (\\"'''+only_disks+'''\\"!=\\"\\" && \\"'''+only_disks+'''\\"!=$4) next; ps=$7*$8/1024/150; if ($5 == \\"r\\") { w_iosize=0 \; r_iosize=ps } else { r_iosize=0 \; w_iosize=ps } print $1\\",\\"$6\\",\\"r_iosize\\",\\"w_iosize }' '''+self.data_fname+'''" using 1:2:3 with points lt rgb "#6c971e" pt 7 ps variable title 'reads', \
#	"" using 1:2:4 with points lt rgb "#0048ff" pt 7 ps variable title 'writes'

#set datafile separator " "

# Bandwidth

set title "I/O access - bandwidth" 
set ylabel "KiB/s"

set output "''' + __cmdLineOpts__.outname + '''_throughput.eps"

plot "''' + fp_g_bwidth.name + '''" using 1:2 with boxes lt 2 title 'Reads (KiB/s)', "" using 1:3 with boxes lt 3 title 'Writes (KiB/s)'

# IOPS

set title "I/O access - I/O operations per second" 
set ylabel "iops"

set output "''' + __cmdLineOpts__.outname + '''_iops.eps"

plot "''' + fp_g_iops.name + '''" using 1:2 with boxes lt 2 title "Reads", "" using 1:3 with boxes lt 3 title "Writes"



''')

# % 		(__cmdLineOpts__.outname, __cmdLineOpts__.outname, only_disks, only_disks, self.data_fname, __cmdLineOpts__.outname, only_disks, only_disks, self.data_fname, __cmdLineOpts__.outname, only_disks, only_disks, self.data_fname) )

		fp.close()

		os.system("""gnuplot %s""" % fname)

		print fname

		# print out summary

		print
		print "Summary:"
		print
		print "\tPeriod analysed: %d seconds" % (sec - first_time)
		print "\tTotal I/O requests: %d" % total_iops.sum
		print "\tAverage IOPS: %s" % human_value(total_iops.avg(), 1000)
		print "\tTotal bytes transferred:", human_byte_sizes(total_bs.sum)
		print "\tAverage throughput: %s/s" % human_byte_sizes(total_bs.sum / ( sec - first_time ) )
		print "\t%s %s" % (total_random, total_bs)
		print

	class ioreplay_engine_class:

		num_worker_threads = 1
		max_queue_size = 1000
		fps = {}
		time_first = None
		time_begin = None
		kindly_stop = False
		read_bytes = 0
		written_bytes = 0

		def __init__(self, ios, read_only = True, make_writes_as_reads = True, speed = 1, disk_to_disk = {}, asap = True, framedrop = False, offset = False):

			from Queue import Queue
			from threading import Thread

			self.asap = asap
			self.disk_to_disk = disk_to_disk
			self.make_writes_as_reads = make_writes_as_reads
			self.framedrop = framedrop
			self.read_only = read_only
			self.speed = speed

			if make_writes_as_reads:
				self.read_only = True

			if framedrop and asap:
				print "notice: can't use framedrop with asap, disabling framedrop."
				self.framedrop = False

			if offset == True:
				self.offset = random.randint(1024 * 1024 * 50, 1024 * 1024 * 100)
				print "using random offset of %d" % offset
			elif offset == False:
				self.offset = 0

			self.queue = Queue(self.max_queue_size)
			self.await = min_avg_max_class("await", base = 1000, unit = "s", thread_safe = True)

			self.pop_thread = Thread(target=self.populate_queue, args = [ios])
			self.pop_thread.setDaemon(True)
			self.pop_thread.start()

			while self.queue.full():
				time.sleep(0.1)

		def start(self):

			from threading import Thread

			self.time_begin = time.time()

			for i in range(self.num_worker_threads): 
				t = Thread(target=self.worker)
				t.setDaemon(True)
				t.start() 

		def populate_queue(self, ios):

			refill = True

			for io in ios:

				if self.kindly_stop:
					return

				while not refill:
					time.sleep(0.5)
					if self.queue.qsize() < self.max_queue_size * 75 / 100:
						refill = True

				self.push(io)

				if self.queue.full():
					refill = False
					continue

		def open_disk(self, io):

			if io.write and self.read_only and not self.make_writes_as_reads: # and os.stat(disk)
				print """Data replay would write to disk %s, but read-only mode is enabled.""" % io.disk
				print """Disable read-only mode or enable "make_writes_as_reads" to convert writes to reads."""
				return False

			if not self.read_only and not self.make_write_as_reads and io.write == True:
				op = "w"
			else:
				op = "r"

			op = "r"

			if io.disk in self.fps.keys() and ( self.fps[io.disk]["mode"] == "w" or self.fps[io.disk]["mode"] == op):
				return self.fps[io.disk]["fp"]

			if io.disk in self.disk_to_disk.keys():
				dev = "/dev/%s" % self.disk_to_disk[io.disk]
			else:
				dev = "/dev/%s" % io.disk

			print """adding device "%s" (will use %s) in %s mode""" % (io.disk, dev, op)

			import directio

			try:
				self.fps[io.disk] = { "fp":directio.open(dev, directio.O_RDONLY, 0644), "mode":op }
			except OSError:
				print "error: could not open %s" % dev
				return False

			return self.fps[io.disk]["fp"]

		def worker(self):

			import directio

			while True:

				if self.kindly_stop:
					return

				io = self.queue.get()

				if not self.time_first:
					self.time_first = io.time

				if not self.asap:
					tdiff = (io.time - self.time_first) / self.speed - ((time.time() - self.time_begin))
					if tdiff > 0:
						time.sleep(tdiff)
					elif tdiff < -0.02 and self.framedrop:
						print "warning: skipping frame (lagging %dms)" % abs(tdiff * 1000)
#						self.skipped_frames += 1
						self.queue.task_done() 
						continue

				io.block = size_align(io.block + self.offset, 512)

				try:
					os.lseek(self.open_disk(io), io.block, 0)
				except OSError:
					print "illegal seek? asked for", io.block
					self.queue.task_done() 
					continue

				timer = time.time()

				done_bytes = 0

				while done_bytes < io.length:

					do_bytes = size_align(io.length - done_bytes, 512)
					do_bytes = min( [512 * 518, do_bytes] )

					txt = directio.read(self.fps[io.disk]["fp"], do_bytes)

					if len(txt) == 0:
						break

					done_bytes += len(txt)

				del txt
				if done_bytes < io.length:
					print "short read/write, block %d, wanted %d bytes, read %d bytes" % (io.block, io.length, done_bytes)

#				print "read/write, block %d, wanted %d bytes, read %d bytes" % (io.block, io.length, done_bytes)

				self.read_bytes += done_bytes

				self.await.push(time.time() - timer)

				self.queue.task_done()

		def push(self, io):

			self.queue.put(io)

		def finished(self):

			return not self.pop_thread.isAlive() and self.queue.empty()

		def terminate(self):

			self.kindly_stop = True

			while not self.queue.empty(): 
				self.queue.get_nowait() 
				self.queue.task_done() 

		def join(self):

			self.queue.join()


	def replay(self, read_only = True, make_writes_as_reads = False, speed = 1, disk_to_disk = {}, asap = False, framedrop = False, offset = False):

		try:
			import directio
		except ImportError:
			print "directio does not appear to be available, I/O replay needs this module to work."
			sys.exit(1)

		io_engine = self.ioreplay_engine_class(ios = self.ios_from_file(), disk_to_disk = disk_to_disk)

		io_engine.start()

		prev_read_bytes = 0
		stats_interval = 5 # seconds
		sec = 0

		try:
			while not io_engine.finished():

				time.sleep(stats_interval)

				print "t:%d iops:%d %s r:%dKiB/s w:0KiB/s" % (sec * stats_interval, io_engine.await.pushed / stats_interval, io_engine.await, (io_engine.read_bytes - prev_read_bytes) / 1024 / stats_interval)

				prev_read_bytes = io_engine.read_bytes
				io_engine.await.clear()
				sec += 1

		except KeyboardInterrupt:
			print "exiting."
			io_engine.terminate()

class IO_Replay_userspace(io_set_class):

	# strace -T -e trace=file -ttt -s 0 -f cat /etc/passwd > /dev/null 

	pass


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
        print "   # tiboo -g -s dump.csv"
        print 
        print """ analyse an I/O dump considering "sdb" only, stop at timestamp 1211881488,\n write output to screen and to file (results.txt):"""
        print 
        print "   # tiboo -s dump.csv -e 1211881488 --only-disk sdb | tee results.txt"
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
__cmdParser__.add_option("-o", metavar="FNAME", \
		     dest="outname", type = "string", default="tmp/graph", \
                     help="base name for output graphs")

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
