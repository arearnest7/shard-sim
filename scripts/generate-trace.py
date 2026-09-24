import numpy as np
import csv
from pathlib import Path
import argparse

headers_out = ["time", "request", "latency", "mem"]
parser = argparse.ArgumentParser(prog="python3 generate-trace.py")
parser.add_argument("--folder_in", default="../trace/requests")
parser.add_argument("--folder_out", default="../trace")
parser.add_argument("--wf_start_max", default=1300000, type=int)
parser.add_argument("--wf_jobs", default=100, type=int)

def main():
	args = parser.parse_args()
	trace = {}
	for i in range(args.wf_jobs):
		wf_start = args.wf_start_max * np.random.rand()
		with open(f'{args.folder_in}/epigenomics-{i}.csv', "r") as f:
			requests_f = csv.DictReader(f)
			requests = []
			for request in requests_f:
				requests.append(request)
			# entry
			if str(wf_start) in trace:
				trace[str(wf_start)].append(requests[0])
			else:
				trace[str(wf_start)] = [requests[0]]
			entry_end = wf_start + float(requests[0]["latency"])
			# fastqSplit
			fastqSplit_end = []
			for j in range(1, 3):
				start = entry_end
				if str(start) in trace:
					trace[str(start)].append(requests[j])
				else:
					trace[str(start)] = [requests[j]]
				fastqSplit_end.append(start + float(requests[j]["latency"]))
			# filterContams
			filterContams_end = []
			for j in range(3, 503):
				start = fastqSplit_end[0]
				if j >= 250:
					start = fastqSplit_end[1]
				if str(start) in trace:
					trace[str(start)].append(requests[j])
				else:
					trace[str(start)] = [requests[j]]
				filterContams_end.append(start + float(requests[j]["latency"]))
			# sol2sanger
			sol2sanger_end = []
			for j in range(503, 1003):
				start = filterContams_end[j-503]
				if str(start) in trace:
					trace[str(start)].append(requests[j])
				else:
					trace[str(start)] = [requests[j]]
				sol2sanger_end.append(start + float(requests[j]["latency"]))
			# fast2bfq
			fast2bfq_end = []
			for j in range(1003, 1503):
				start = sol2sanger_end[j-1003]
				if str(start) in trace:
					trace[str(start)].append(requests[j])
				else:
					trace[str(start)] = [requests[j]]
				fast2bfq_end.append(start + float(requests[j]["latency"]))
			# map
			map_end = []
			for j in range(1503, 2003):
				start = fast2bfq_end[j-1503]
				if str(start) in trace:
					trace[str(start)].append(requests[j])
				else:
					trace[str(start)] = [requests[j]]
				map_end.append(start + float(requests[j]["latency"]))
			# mapMerge1 (2)
			mapMerge1_end = []
			for j in range(2003, 2005):
				sub_arr = map_end[:250]
				if j == 2004:
					sub_arr = map_end[250:]
				start = np.array(sub_arr).max()
				if str(start) in trace:
					trace[str(start)].append(requests[j])
				else:
					trace[str(start)] = [requests[j]]
				mapMerge1_end.append(start + float(requests[j]["latency"]))
			# mapMerge2 (1)
			start = np.array(mapMerge1_end).max()
			if str(start) in trace:
				trace[str(start)].append(requests[2005])
			else:
				trace[str(start)] = [requests[2005]]
			mapMerge2_end = start + float(requests[2005]["latency"])
			# chr21
			start = mapMerge2_end
			if str(start) in trace:
				trace[str(start)].append(requests[2006])
			else:
				trace[str(start)] = [requests[2006]]
			chr21_end = start + float(requests[2006]["latency"])
			# pileup
			start = chr21_end
			if str(start) in trace:
				trace[str(start)].append(requests[2007])
			else:
				trace[str(start)] = [requests[2007]]
			print("finished processing workflow: " + str(i))
	times = []
	for time in trace.keys():
		times.append(float(time))
	times.sort()
	with open(f'{args.folder_out}/trace.csv', "w") as f:
		writer = csv.DictWriter(f, fieldnames=headers_out)
		writer.writeheader()
		requests = []
		for time in times:
			print("writing event at: " + str(time))
			requests = []
			for request in trace[str(time)]:
				requests.append({"time": str(time), "request": request["request"], "latency": request["latency"], "mem": request["mem"]})
			writer.writerows(requests)
main()
