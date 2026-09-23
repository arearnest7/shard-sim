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
parser.add_argument("--baseline_standard_w_ttl", default="baseline-standard-ttl_180000-target_20")
parser.add_argument("--baseline_standard_wo_ttl", default="baseline-standard-ttl_0-target_20")
parser.add_argument("--baseline_exact_wo_ttl", default="baseline-exact-ttl_0-target_20")
parser.add_argument("--arbiter", default="arbiter-standard-ttl_180000-target_20")
parser.add_argument("--k_container_create", default=1000, type=int) # measured in ms
parser.add_argument("--k_container_delete", default=1000, type=int) # measured in ms
parser.add_argument("--k_container_modify", default=1000, type=int) # measured in ms
parser.add_argument("--k_cgroup_create", default=1, type=int) # measured in ms
parser.add_argument("--k_cgroup_delete", default=500, type=int) # measured in ms
parser.add_argument("--k_cgroup_modify", default=1, type=int) # measured in ms
parser.add_argument("--k_event_cost", default=100, type=int) # measured in MB/ms

def main():
	args = parser.parse_args()
	Path(args.folder_out).mkdir(parents=True, exist_ok=True)
	t_ms = range(2000000)
	workflow_ids = range(10000)
	variants = {
		"baseline-standard-w-ttl": ["r.", args.baseline_standard_w_ttl, 1],
		"baseline-standard-wo-ttl": ["m.", args.baseline_standard_wo_ttl, 1],
		"baseline-exact": ["c.", args.baseline_exact_wo_ttl, 1],
		"arbiter": ["g.", args.arbiter, 1]
	}
	k_weight = {
		"container": {"create": args.k_container_create, "delete": args.k_container_delete, "modify": args.k_container_modify},
		"cgroup": {"create": args.k_cgroup_create, "delete": args.k_cgroup_delete, "modify": args.k_cgroup_modify}
	}
	k_events = {}
	k_overhead = {}
	k_total_events = {}
	k_total_overhead = {}
	memory_allocated = {}
	memory_idle = {}
	memory_allocated_k = {}
	memory_idle_k = {}
	memory_used = []
	peaks = {}
	memory_costs = {}
	memory_costs_p = {}
	# incoming mem = MB, time = ms
	# convert to GB (/ 1000)
	# convert to GB*s (/ 1000 / 1000)
	for variant, val in variants.items():
		memory_allocated[variant] = []
		memory_idle[variant] = []
		memory_allocated_k[variant] = []
		memory_idle_k[variant] = []
		memory_costs[variant] = []
		memory_costs_p[variant] = {}
		peaks[variant] = {}
		k_events[variant] = {
			"container": {"create": [], "delete": [], "modify": []},
			"cgroup": {"create": [], "delete": [], "modify": []}
		}
		k_overhead[variant] = {
			"container": {"create": [], "delete": [], "modify": []},
			"cgroup": {"create": [], "delete": [], "modify": []}
		}
		k_total_events[variant] = {
			"container": {"create": 0, "delete": 0, "modify": 0},
			"cgroup": {"create": 0, "delete": 0, "modify": 0}
		}
		k_total_overhead[variant] = 0
		for source in ["timeline", "peak", "cost", "k"]:
			file = f'{args.folder_in}/{val[1]}-{source}.csv'
			with open(file, "r") as f:
				file_in = csv.DictReader(f)
				if source == "timeline":
					for t in file_in:
						if variant == "arbiter":
							memory_used.append(round(float(t["used_total"]), 3) / 1000)
						memory_allocated[variant].append(round(float(t["alloc_total"]), 3) / 1000)
						memory_idle[variant].append(round(float(t["idle_total"]), 3) / 1000)
				elif source == "peak":
					for data in file_in:
						for peak in ["alloc_total", "used_total", "idle_total"]:
							peaks[variant][peak] = round(float(data[peak]), 3) / 1000
				elif source == "cost":
					for data in file_in:
						for workflow_id in workflow_ids:
							memory_costs[variant].append(round(float(data[str(workflow_id)]), 3) / 1000 / 1000)
					for p in [50, 95, 99]:
						memory_costs_p[variant][str(p)] = np.percentile(memory_costs[variant], p)
				elif source == "k":
					for data in file_in:
						for c in ["container", "cgroup"]:
							for m in ["create", "delete", "modify"]:
								d = round(float(data[f'{c}_{m}']), 3)
								k_events[variant][c][m].append(d)
								k_total_events[variant][c][m] += d
								k_overhead[variant][c][m].append(d * k_weight[c][m] / 1000)
					for c in ["container", "cgroup"]:
						for m in ["create", "delete", "modify"]:
							k_total_overhead[variant] += k_total_events[variant][c][m] * k_weight[c][m] / 1000
	for variant, val in variants.items():
		for i in range(len(memory_allocated[variant])):
			memory_allocated_k[variant].append(memory_allocated[variant][i] + k_total_overhead[variant] * args.k_event_cost / 2000000) # GB + (s*1000) * (MB/ms / 1000) / ms * 1ms = GB + (ms)(GB/ms)(ms)/(ms) = GB + GB
			memory_idle_k[variant].append(memory_idle[variant][i] + k_total_overhead[variant] * args.k_event_cost / 2000000)
	# graph memory allocated over time (GB vs. ms) (baselines, arbiter, used)
	mem_allocated, ax = plt.subplots(1)
	ax.set_title("Memory Allocated over Time")
	ax.set_xlabel("Time (ms)")
	ax.set_ylabel("Memory Allocated (GB)")
	for variant, marker in variants.items():
		ax.plot(t_ms, memory_allocated[variant], marker[0], label=variant, alpha=marker[2])
	ax.plot(t_ms, memory_used, "k-", label="used")
	ax.legend(loc='upper right')
	mem_allocated.savefig(f'{args.folder_out}/mem_allocated.png', dpi=300)
	# graph memory idle over time (GB vs. ms) (baselines, arbiter)
	mem_idle, ax = plt.subplots(1)
	ax.set_title("Memory Idle over Time")
	ax.set_xlabel("Time (ms)")
	ax.set_ylabel("Memory Idle (GB)")
	for variant, marker in variants.items():
		ax.plot(t_ms, memory_idle[variant], marker[0], label=variant, alpha=marker[2])
	ax.legend(loc='upper right')
	mem_idle.savefig(f'{args.folder_out}/mem_idle.png', dpi=300)
	# graph memory allocated over time w/ averaged k-event cost (GB vs. ms) (baselines, arbiter, used)
	mem_allocated_k, ax = plt.subplots(1)
	ax.set_title("Memory Allocated over Time w/ Factored K-Event Cost")
	ax.set_xlabel("Time (ms)")
	ax.set_ylabel("Memory Allocated (GB)")
	for variant, marker in variants.items():
		ax.plot(t_ms, memory_allocated_k[variant], marker[0], label=variant, alpha=marker[2])
	ax.plot(t_ms, memory_used, "k-", label="used")
	ax.legend(loc='upper right')
	mem_allocated_k.savefig(f'{args.folder_out}/mem_allocated_k.png', dpi=300)
	# graph memory idle over time w/ averaged k-event cost (GB vs. ms) (baselines, arbiter)
	mem_idle_k, ax = plt.subplots(1)
	ax.set_title("Memory Idle over Time w/ Factored K-Event Cost")
	ax.set_xlabel("Time (ms)")
	ax.set_ylabel("Memory Idle (GB)")
	for variant, marker in variants.items():
		ax.plot(t_ms, memory_idle_k[variant], marker[0], label=variant, alpha=marker[2])
	ax.legend(loc='upper right')
	mem_idle_k.savefig(f'{args.folder_out}/mem_idle_k.png', dpi=300)
	# table peak alloc/idle memory (GB) (baselines, arbiter)
	peak_table, ax = plt.subplots()
	peak_table.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	peak_columns = ["", "Allocated (GB)", "Idle (GB)"]
	peak_vals = []
	for variant in variants.keys():
		peak_vals.append([variant, round(peaks[variant]["alloc_total"], 3), round(peaks[variant]["idle_total"], 3)])
	ax.table(cellText=peak_vals, colLabels=peak_columns, loc="center")
	peak_table.tight_layout()
	peak_table.savefig(f'{args.folder_out}/peak_table.png', dpi=300)
	# table of memory cost (GB*s) P50, P95, P99 (baselines, arbiter)
	memory_cost_percentile, ax = plt.subplots()
	memory_cost_percentile.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	percentile_columns = ["", "P50", "P95", "P99"]
	percentile_vals = []
	for variant in variants.keys():
		percentile_vals.append([variant, f'{round(memory_costs_p[variant]["50"], 2)} GB*s', f'{round(memory_costs_p[variant]["95"], 2)} GB*s', f'{round(memory_costs_p[variant]["99"], 2)} GB*s'])
	ax.table(cellText=percentile_vals, colLabels=percentile_columns, loc="center")
	memory_cost_percentile.tight_layout()
	memory_cost_percentile.savefig(f'{args.folder_out}/memory_cost_percentile.png', dpi=300)
	# table of creation, deletion or modification latency overhead (container, cgroup)
	k_weights_table, ax = plt.subplots()
	k_weights_table.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	overheads = []
	for c in ["container", "cgroup"]:
		overhead_line = [c]
		for m in ["create", "delete", "modify"]:
			overhead_line.append(f'{k_weight[c][m]} ms')
		overheads.append(overhead_line)
	overhead_columns = ["", "creation", "deletion", "modification"]
	ax.table(cellText=overheads, colLabels=overhead_columns, loc="center")
	k_weights_table.tight_layout()
	k_weights_table.savefig(f'{args.folder_out}/k_weights_table.png', dpi=300)
	# table of overhead for k events by variant
	k_latency_overhead, ax = plt.subplots()
	k_latency_overhead.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	overheads = []
	for variant, vals in variants.items():
		overheads.append([variant, f'{round(k_total_overhead[variant], 1)} s'])
	overhead_columns = ["", "cumulative latency overhead"]
	ax.table(cellText=overheads, colLabels=overhead_columns, loc="center")
	k_latency_overhead.tight_layout()
	k_latency_overhead.savefig(f'{args.folder_out}/k_latency_overhead.png', dpi=300)
	# table of total k events by variant
	k_total_events_table, ax = plt.subplots()
	k_total_events_table.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	k_totals = []
	for variant, vals in variants.items():
		var_line = [variant]
		for c in ["container", "cgroup"]:
			for m in ["create", "delete", "modify"]:
				var_line.append(k_total_events[variant][c][m])
		k_totals.append(var_line)
	event_columns = ["", "container creation", "container deletion", "container modification", "cgroup creation", "cgroup deletion", "cgroup modification"]
	ax.table(cellText=k_totals, colLabels=event_columns, loc="center")
	k_total_events_table.tight_layout()
	k_total_events_table.savefig(f'{args.folder_out}/k_total_events_table.png', dpi=300)
	# table of average per request k events by variant
	k_events_table, ax = plt.subplots()
	k_events_table.patch.set_visible(True)
	ax.axis("off")
	ax.axis("tight")
	k_list = []
	for variant, vals in variants.items():
		var_line = [variant]
		for c in ["container", "cgroup"]:
			for m in ["create", "delete", "modify"]:
				var_line.append(round(np.average(k_events[variant][c][m]), 2))
		k_list.append(var_line)
	event_columns = ["", "container creation", "container deletion", "container modification", "cgroup creation", "cgroup deletion", "cgroup modification"]
	ax.table(cellText=k_list, colLabels=event_columns, loc="center")
	k_events_table.tight_layout()
	k_events_table.savefig(f'{args.folder_out}/k_events_table.png', dpi=300)

main()
