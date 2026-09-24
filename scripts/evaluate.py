import csv
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import math
import argparse

parser = argparse.ArgumentParser(prog="python3 evaluate.py")
parser.add_argument("--folder_in", default="../simulation")
parser.add_argument("--folder_out", default="../evaluation-figs")
parser.add_argument("--knative_standard_w_ttl", default="knative-standard-ttl_180000-target_20")
parser.add_argument("--knative_standard_wo_ttl", default="knative-standard-ttl_0-target_20")
parser.add_argument("--shard", default="shard-standard-ttl_180000-target_20")
parser.add_argument("--modification_container_create", default=1000, type=int) # measured in ms
parser.add_argument("--modification_container_delete", default=1000, type=int) # measured in ms
parser.add_argument("--modification_container_modify", default=1000, type=int) # measured in ms
parser.add_argument("--modification_cgroup_create", default=1, type=int) # measured in ms
parser.add_argument("--modification_cgroup_delete", default=500, type=int) # measured in ms
parser.add_argument("--modification_cgroup_modify", default=1, type=int) # measured in ms
parser.add_argument("--total_time", default=2000000, type=int) # ms
parser.add_argument("--wf_jobs", default=100, type=int)

def main():
	args = parser.parse_args()
	Path(args.folder_out).mkdir(parents=True, exist_ok=True)
	t_s = []
	for i in range(args.total_time):
		t_s.append(i / 1000)
	variants = {
		"knative-w-ttl": ["r.", args.knative_standard_w_ttl, 1],
		"knative-wo-ttl": ["m.", args.knative_standard_wo_ttl, 1],
		"shard": ["g.", args.shard, 1]
	}
	modification_weight = {
		"container": {"create": args.modification_container_create, "delete": args.modification_container_delete, "modify": args.modification_container_modify},
		"cgroup": {"create": args.modification_cgroup_create, "delete": args.modification_cgroup_delete, "modify": args.modification_cgroup_modify}
	}
	modification_events = {}
	modification_total_events = {}
	memory_allocated = {}
	memory_allocated_percentile = {}
	peaks = {}
	# incoming mem = MB, time = ms
	# convert to GB (/ 1000)
	# convert to GB*s (/ 1000 / 1000)
	for variant, val in variants.items():
		memory_allocated[variant] = []
		memory_allocated_percentile[variant] = []
		peaks[variant] = {}
		modification_events[variant] = {
			"container": {"create": [], "delete": [], "modify": []},
			"cgroup": {"create": [], "delete": [], "modify": []}
		}
		modification_total_events[variant] = {
			"container": {"create": 0, "delete": 0, "modify": 0},
			"cgroup": {"create": 0, "delete": 0, "modify": 0}
		}
		for source in ["timeline", "peak", "modifications"]:
			file = f'{args.folder_in}/{val[1]}-{source}.csv'
			with open(file, "r") as f:
				file_in = csv.DictReader(f)
				if source == "timeline":
					for t in file_in:
						memory_allocated[variant].append(round(float(t["alloc_total"]), 3) / 1000)
					for i in range(len(memory_allocated[variant])):
						if memory_allocated["knative-w-ttl"][i] > 0:
							memory_allocated_percentile[variant].append(memory_allocated[variant][i] / memory_allocated["knative-w-ttl"][i])
						else:
							memory_allocated_percentile[variant].append(1)
				elif source == "peak":
					for data in file_in:
						for peak in ["alloc_total", "used_total", "idle_total"]:
							peaks[variant][peak] = round(float(data[peak]), 3) / 1000
				elif source == "modifications":
					for data in file_in:
						for c in ["container", "cgroup"]:
							for m in ["create", "delete", "modify"]:
								d = round(float(data[f'{c}_{m}']), 3)
								modification_events[variant][c][m].append(d)
								modification_total_events[variant][c][m] += d
	# graph of memory allocation over time (GB vs s) (knative, shard)
	mem_allocated, ax = plt.subplots(1)
	ax.set_title("Memory Allocated over Time")
	ax.set_xlabel("Time (s)")
	ax.set_ylabel("Memory Allocated (GB)")
	for variant, marker in variants.items():
		ax.plot(t_s, memory_allocated[variant], marker[0], label=variant, alpha=marker[2])
	ax.legend(loc='upper right')
	mem_allocated.savefig(f'{args.folder_out}/mem_allocated.png', dpi=1200)
	# table of peak memory (allocated, idle) (knative, shard)
	peak_table, ax = plt.subplots()
	peak_table.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	peak_columns = ["", "Allocated", "Idle"]
	peak_vals = []
	for variant in variants.keys():
		peak_vals.append([variant, f'{round(peaks[variant]["alloc_total"], 1)} GB', f'{round(peaks[variant]["idle_total"], 1)} GB'])
	ax.table(cellText=peak_vals, colLabels=peak_columns, loc="center")
	peak_table.tight_layout()
	peak_table.savefig(f'{args.folder_out}/peak_table.png', dpi=1200)
	# bar graph of peak memory (allocated, idle) (knative, shard)
	peak_bar, ax = plt.subplots()
	peak_bar.patch.set_visible(True)
	ax.set_title("Peak Memory Allocated and Idle")
	peak_columns = ["Allocated", "Idle"]
	for variant in variants.keys():
		ax.bar(peak_columns, [peaks[variant]["alloc_total"], peaks[variant]["idle_total"]], label=variant)
	ax.set_ylabel("Memory (GB)")
	peak_bar.savefig(f'{args.folder_out}/peak_bar.png', dpi=1200)
	# table of abstraction modifications per variant (total, per-job) (knative, shard)
	modification_events_table, ax = plt.subplots()
	modification_events_table.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	modification_totals = []
	for variant, vals in variants.items():
		var_line_total = [f'{variant} total']
		var_line_per_job = [f'{variant} per-job']
		for c in ["container", "cgroup"]:
			for m in ["create", "delete", "modify"]:
				var_line_total.append(f'{modification_total_events[variant][c][m]}')
				var_line_per_job.append(f'{np.average(modification_events[variant][c][m])}')
		modification_totals.append(var_line_total)
		modification_totals.append(var_line_per_job)
	event_columns = ["", "container creation", "container deletion", "container modification", "cgroup creation", "cgroup deletion", "cgroup modification"]
	ax.table(cellText=modification_totals, colLabels=event_columns, loc="center")
	modification_events_table.tight_layout()
	modification_events_table.savefig(f'{args.folder_out}/modification_events_table.png', dpi=1200)
	# table of workflow latency P50, P95, P99 w/ factored abstraction modification overhead (ideal, knative, shard)
	
	# graph of percent memory allocation difference w/ respect to knative w/ ttl (knative w/o ttl, shard)
	mem_allocated_normalized, ax = plt.subplots(1)
	ax.set_title("Memory Allocated over Time Normalized w/ Respect to Knative w/ TTL")
	ax.set_xlabel("Time (s)")
	ax.set_ylabel("Memory Allocated (GB)")
	for variant, marker in variants.items():
		ax.plot(t_s, memory_allocated_percentile[variant], marker[0], label=variant, alpha=marker[2])
	ax.legend(loc='upper right')
	mem_allocated_normalized.savefig(f'{args.folder_out}/mem_allocated_normalized.png', dpi=1200)
	# table of abstraction modification costs
	modification_weights_table, ax = plt.subplots()
	modification_weights_table.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	overheads = []
	for c in ["container", "cgroup"]:
		overhead_line = [c]
		for m in ["create", "delete", "modify"]:
			overhead_line.append(f'{modification_weight[c][m]} ms')
		overheads.append(overhead_line)
	overhead_columns = ["", "creation", "deletion", "modification"]
	ax.table(cellText=overheads, colLabels=overhead_columns, loc="center")
	modification_weights_table.tight_layout()
	modification_weights_table.savefig(f'{args.folder_out}/modification_weights_table.png', dpi=1200)

main()
