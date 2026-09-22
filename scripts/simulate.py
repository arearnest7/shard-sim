import numpy as np
import csv
from pathlib import Path
import math
import argparse
import datetime

parser = argparse.ArgumentParser(prog="python3 simulate.py")
parser.add_argument("--folder", default="../simulation")
parser.add_argument("--scheduler", default="baseline")
parser.add_argument("--ttl", default=180000, type=int) # measured in ms
parser.add_argument("--target", default=20, type=int)
parser.add_argument("--assignment", default="standard")
#parser.add_argument("--k_container_create", default=1000, type=int) # measured in ms
#parser.add_argument("--k_container_delete", default=1000, type=int) # measured in ms
#parser.add_argument("--k_container_modify", default=1000, type=int) # measured in ms
#parser.add_argument("--k_cgroup_create", default=1, type=int) # measured in ms
#parser.add_argument("--k_cgroup_delete", default=500, type=int) # measured in ms
#parser.add_argument("--k_cgroup_modify", default=1, type=int) # measured in ms

mu_sigma = {
	"entry": {"mu": 1.0, "sigma": 0.0},
	"fastqSplit": {"mu": 100.0, "sigma": 10.0},
	"filterContams": {"mu": 65.0, "sigma": 8.0},
	"sol2sanger": {"mu": 45.0, "sigma": 8.0},
	"fast2bfq": {"mu": 80.0, "sigma": 7.0},
	"map": {"mu": 185.0, "sigma": 5.0},
	"mapMerge1": {"mu": 120.0, "sigma": 10.0},
	"mapMerge2": {"mu": 120.0, "sigma": 10.0},
	"chr21": {"mu": 55.0, "sigma": 7.0},
	"pileup": {"mu": 95.0, "sigma": 12.0}
}

total_time = 2000000 # ms

instances = {}
# workflow_id: {allocated_total: mem, shards: {shard_id: {in_process: request, allocated: mem, last_invoked: time, owner: function_name}}}
# function_name: {instance_id: {in_process: {request}, allocated: mem, last_invoked: time, owner: {workflow_id}}}

next_event = {}
# key: ms, value: {workflow_id: {shard_id}}
# key: ms, value: {function_name: {instance_id}}

no_process = {}
# key: workflow_id, value: {shard_id: 1}
# key: function_name, value: {instance_id: 1}

total_deployed = {}
allocated = {} # key: workflow_id, value: float
memory_cost = {} # in units of MB*ms
k_events = {"container": {"create": {}, "delete": {}, "modify": {}}, "cgroup": {"create": {}, "delete": {}, "modify": {}}}

stats = {"time": 0, "alloc_total": 0, "used_total": 0, "idle_total": 0}
peak = {"alloc_total": 0, "used_total": 0, "idle_total": 0}
container_alloc = {}

def main():
	args = parser.parse_args()
	for function, stat_line in mu_sigma.items():
		if args.scheduler == "baseline":
			instances[function] = {}
			no_process[function] = {}
		stats["alloc_" + function] = 0
		stats["used_" + function] = 0
		stats["idle_" + function] = 0
		peak["alloc_" + function] = 0
		peak["used_" + function] = 0
		peak["idle_" + function] = 0
		if args.scheduler == "baseline":
			total_deployed[function] = 0
			container_alloc[function] = (stat_line["mu"] + 3 * stat_line["sigma"]) * args.target
	Path(args.folder).mkdir(parents=True, exist_ok=True)
	with open(f'../trace/trace.csv', "r") as t:
		requests = csv.DictReader(t)
		sim_file = f'{args.folder}/{args.scheduler}-{args.assignment}-ttl_{args.ttl}-target_{args.target}-timeline.csv'
		with open(sim_file, "w") as f:
			writer = csv.DictWriter(f, fieldnames=stats.keys())
			writer.writeheader()
			for incoming_request in requests:
				while stats["time"] < math.floor(float(incoming_request["time"])):
					if str(stats["time"]) in next_event:
						if args.scheduler == "arbiter":
							for workflow_id, shard_ids in next_event[str(stats["time"])].items():
								for shard_id in shard_ids:
									if instances[workflow_id]["shards"][shard_id]["process"] != None:
										to_delete = False
										if float(instances[workflow_id]["shards"][shard_id]["process"]["time"]) + float(instances[workflow_id]["shards"][shard_id]["process"]["latency"]) < stats["time"]: # request done, returning to idle
											mem_shard = float(instances[workflow_id]["shards"][shard_id]["process"]["mem"])
											instances[workflow_id]["allocated_total"] -= mem_shard
											instances[workflow_id]["shards"][shard_id]["allocated"] = 0 # in practice this shrinks/expands to the next stage, but its a linear trace and I am not rebuilding the topology graphs as inputs (16+GB in memory); its corrected by the search for pre-existing in the next block
											stats["used_total"] -= mem_shard
											stats["used_" + instances[workflow_id]["shards"][shard_id]["owner"]] -= mem_shard
											stats["alloc_total"] -= mem_shard
											stats["alloc_" + instances[workflow_id]["shards"][shard_id]["owner"]] -= mem_shard
											instances[workflow_id]["shards"][shard_id]["process"] = None
											no_process[workflow_id][shard_id] = 1
											if len(no_process[workflow_id]) == len(instances[workflow_id]["shards"]): # final function executed, shutting down (we know what the last function is beforehand)
												to_delete = True
										if to_delete:
											k_events["container"]["delete"][workflow_id] += 1
											del no_process[workflow_id]
											del instances[workflow_id]
						else:
							for function_name, instance_ids in next_event[str(stats["time"])].items():
								for instance_id, targets in instance_ids.items():
									for target, c in targets.items():
										if instance_id in instances[function_name]:
											if (instance_id not in no_process[function_name] or target not in no_process[function_name][instance_id]) and float(instances[function_name][instance_id]["process"][target]["time"]) + float(instances[function_name][instance_id]["process"][target]["latency"]) < stats["time"]: # request done, returning to idle
												mem_process = float(instances[function_name][instance_id]["process"][target]["mem"])
												stats["used_total"] -= mem_process
												stats["used_" + function_name] -= mem_process
												stats["idle_total"] += mem_process
												stats["idle_" + function_name] += mem_process
												if args.assignment == "exact":
													k_events["container"]["modify"][instances[function_name][instance_id]["owner"][target]] += 1
												if instances[function_name][instance_id]["owner"][target] in allocated:
													if args.assignment == "exact":
														allocated[instances[function_name][instance_id]["owner"][target]] -= mem_process
														instances[function_name][instance_id]["allocated"] -= mem_process
														stats["alloc_total"] -= mem_process
														stats["alloc_" + function_name] -= mem_process
														stats["idle_total"] -= mem_process
														stats["idle_" + function_name] -= mem_process
													if allocated[instances[function_name][instance_id]["owner"][target]] < 1:
														del allocated[instances[function_name][instance_id]["owner"][target]]
												if instance_id not in no_process[function_name]:
													no_process[function_name][instance_id] = {}
												no_process[function_name][instance_id][target] = 1
											if instances[function_name][instance_id]["last_invoked"] + args.ttl < stats["time"] and instance_id in no_process[function_name] and len(no_process[function_name][instance_id]) == args.target: # ttl reclaim
												if args.assignment == "standard":
													for t, owner in instances[function_name][instance_id]["owner"].items():
														allocated[owner] -= container_alloc[function_name] / args.target
												k_events["container"]["delete"][instances[function_name][instance_id]["owner"][target]] += 1
												mem_allocated = instances[function_name][instance_id]["allocated"]
												stats["idle_total"] -= mem_allocated
												stats["idle_" + function_name] -= mem_allocated
												stats["alloc_total"] -= mem_allocated
												stats["alloc_" + function_name] -= mem_allocated
												del instances[function_name][instance_id]
												if instance_id in no_process[function_name]:
													del no_process[function_name][instance_id]
					for stat_name, stat in stats.items(): # update the peak
						if stat_name != "time" and peak[stat_name] < stat:
							peak[stat_name] = stat
					if args.scheduler == "arbiter":
						for workflow_id, instance in instances.items(): # has not been reclaimed and needs to be "billed"
							memory_cost[workflow_id] += instance["allocated_total"]
						writer.writerow(stats) # write simulation timeline
					else:
						to_delete = []
						for workflow_id in allocated:
							if allocated[workflow_id] < 1:
								to_delete.append(workflow_id)
						for workflow_id in to_delete:
							del allocated[workflow_id]
						for workflow_id, alloc in allocated.items():
							memory_cost[workflow_id] += alloc
						writer.writerow(stats)
					stats["time"] += 1
					if stats["time"] % 1000 == 0:
						print("simulation time (ms): " + str(stats["time"]))
				wf_id = incoming_request["request"].split("_")[1]
				if wf_id not in k_events["container"]["create"]:
					for c in ["container", "cgroup"]:
						for m in ["create", "delete", "modify"]:
							k_events[c][m][wf_id] = 0
				function_name = incoming_request["request"].split("_")[2]
				if args.scheduler == "arbiter":
					if wf_id not in instances:
						k_events["container"]["create"][wf_id] += 1
						instances[wf_id] = {"allocated_total": 0, "shards": {}}
						memory_cost[wf_id] = 0
						no_process[wf_id] = {}
					if len(no_process[wf_id]) > 0: # find pre-existing idle shard for incoming request
						shard_id = next(iter(no_process[wf_id]))
						del no_process[wf_id][shard_id]
						instances[wf_id]["shards"][shard_id]["process"] = incoming_request
						instances[wf_id]["shards"][shard_id]["last_invoked"] = float(incoming_request["time"])
						instances[wf_id]["shards"][shard_id]["owner"] = function_name
						instances[wf_id]["shards"][shard_id]["allocated"] = float(incoming_request["mem"])
						k_events["cgroup"]["modify"][wf_id] += 2 # counting external and shard
						instances[wf_id]["allocated_total"] += instances[wf_id]["shards"][shard_id]["allocated"]
						stats["used_total"] += float(incoming_request["mem"])
						stats["used_" + function_name] += float(incoming_request["mem"])
						stats["alloc_total"] += float(incoming_request["mem"])
						stats["alloc_" + function_name] += float(incoming_request["mem"])
						next_finish = str(int(math.ceil(float(instances[wf_id]["shards"][shard_id]["process"]["time"]) + float(instances[wf_id]["shards"][shard_id]["process"]["latency"]))))
						if next_finish not in next_event:
							next_event[next_finish] = {}
						if wf_id not in next_event[next_finish]:
							next_event[next_finish][wf_id] = {}
						next_event[next_finish][wf_id][shard_id] = 1
					else: # create new shard for incoming request
						k_events["cgroup"]["create"][wf_id] += 1
						shard_id = len(instances[wf_id]["shards"])
						instances[wf_id]["shards"][shard_id] = {"process": incoming_request, "allocated": float(incoming_request["mem"]), "last_invoked": float(incoming_request["time"]), "owner": function_name}
						instances[wf_id]["allocated_total"] += instances[wf_id]["shards"][shard_id]["allocated"]
						stats["used_total"] += float(incoming_request["mem"])
						stats["used_" + function_name] += float(incoming_request["mem"])
						stats["alloc_total"] += float(incoming_request["mem"])
						stats["alloc_" + function_name] += float(incoming_request["mem"])
						next_finish = str(int(math.ceil(float(instances[wf_id]["shards"][shard_id]["process"]["time"]) + float(instances[wf_id]["shards"][shard_id]["process"]["latency"]))))
						if next_finish not in next_event:
							next_event[next_finish] = {}
						if wf_id not in next_event[next_finish]:
							next_event[next_finish][wf_id] = {}
						next_event[next_finish][wf_id][shard_id] = 1
				else:
					if wf_id not in allocated:
						allocated[wf_id] = 0
					if wf_id not in memory_cost:
						memory_cost[wf_id] = 0
					if len(no_process[function_name]) > 0: # find pre-existing idle instance for incoming request
						instance_id = next(iter(no_process[function_name]))
						target = next(iter(no_process[function_name][instance_id]))
						prev_owner = instances[function_name][instance_id]["owner"][target]
						instances[function_name][instance_id]["process"][target] = incoming_request
						instances[function_name][instance_id]["last_invoked"] = float(incoming_request["time"])
						instances[function_name][instance_id]["owner"][target] = wf_id
						if args.assignment == "standard":
							if prev_owner != wf_id:
								allocated[prev_owner] -= container_alloc[function_name] / args.target
								allocated[instances[function_name][instance_id]["owner"][target]] += container_alloc[function_name] / args.target
							stats["idle_total"] -= float(incoming_request["mem"])
							stats["idle_" + function_name] -= float(incoming_request["mem"])
						elif args.assignment == "exact":
							allocated[instances[function_name][instance_id]["owner"][target]] += float(incoming_request["mem"])
							instances[function_name][instance_id]["allocated"] += float(incoming_request["mem"])
							stats["alloc_total"] += float(incoming_request["mem"])
							stats["alloc_" + function_name] += float(incoming_request["mem"])
							k_events["container"]["modify"][wf_id] += 1
						stats["used_total"] += float(incoming_request["mem"])
						stats["used_" + function_name] += float(incoming_request["mem"])
						next_finish = int(math.ceil(float(instances[function_name][instance_id]["process"][target]["time"]) + float(instances[function_name][instance_id]["process"][target]["latency"])))
						next_ttl = int(math.ceil(instances[function_name][instance_id]["last_invoked"] + args.ttl))
						if next_ttl < next_finish:
							next_ttl = next_finish
						if str(next_finish) not in next_event:
							next_event[str(next_finish)] = {}
						if function_name not in next_event[str(next_finish)]:
							next_event[str(next_finish)][function_name] = {}
						if instance_id not in next_event[str(next_finish)][function_name]:
							next_event[str(next_finish)][function_name][instance_id] = {}
						if str(next_ttl) not in next_event:
							next_event[str(next_ttl)] = {}
						if function_name not in next_event[str(next_ttl)]:
							next_event[str(next_ttl)][function_name] = {}
						if instance_id not in next_event[str(next_ttl)][function_name]:
							next_event[str(next_ttl)][function_name][instance_id] = {}
						next_event[str(next_finish)][function_name][instance_id][target] = 1
						next_event[str(next_ttl)][function_name][instance_id][target] = 1
						del no_process[function_name][instance_id][target]
						if len(no_process[function_name][instance_id]) == 0:
							del no_process[function_name][instance_id]
					else: # create new instance for incoming request
						k_events["container"]["create"][wf_id] += 1
						mem_alloc = container_alloc[function_name]
						instance_id = str(total_deployed[function_name])
						if args.assignment == "exact":
							mem_alloc = float(incoming_request["mem"])
						targets = {"0": incoming_request}
						owners = {"0": wf_id}
						if args.target > 1:
							no_process[function_name][instance_id] = {}
							for target in range(args.target-1):
								no_process[function_name][instance_id][str(target+1)] = 1
								owners[str(target+1)] = wf_id
						instances[function_name][str(total_deployed[function_name])] = {"process": targets, "allocated": mem_alloc, "last_invoked": float(incoming_request["time"]), "owner": owners}
						if args.assignment == "standard":
							allocated[instances[function_name][instance_id]["owner"]["0"]] += container_alloc[function_name]
						elif args.assignment == "exact":
							allocated[instances[function_name][instance_id]["owner"]["0"]] += float(incoming_request["mem"])
						stats["used_total"] += float(incoming_request["mem"])
						stats["used_" + function_name] += float(incoming_request["mem"])
						stats["idle_total"] += mem_alloc - float(incoming_request["mem"])
						stats["idle_" + function_name] += mem_alloc - float(incoming_request["mem"])
						stats["alloc_total"] += mem_alloc
						stats["alloc_" + function_name] += mem_alloc
						next_finish = int(math.ceil(float(instances[function_name][instance_id]["process"]["0"]["time"]) + float(instances[function_name][instance_id]["process"]["0"]["latency"])))
						next_ttl = int(math.ceil(instances[function_name][instance_id]["last_invoked"] + args.ttl))
						if next_ttl < next_finish:
							next_ttl = next_finish
						if str(next_finish) not in next_event:
							next_event[str(next_finish)] = {}
						if function_name not in next_event[str(next_finish)]:
							next_event[str(next_finish)][function_name] = {}
						if instance_id not in next_event[str(next_finish)][function_name]:
							next_event[str(next_finish)][function_name][instance_id] = {}
						if str(next_ttl) not in next_event:
							next_event[str(next_ttl)] = {}
						if function_name not in next_event[str(next_ttl)]:
							next_event[str(next_ttl)][function_name] = {}
						if instance_id not in next_event[str(next_ttl)][function_name]:
							next_event[str(next_ttl)][function_name][instance_id] = {}
						next_event[str(next_finish)][function_name][instance_id]["0"] = 1
						next_event[str(next_ttl)][function_name][instance_id]["0"] = 1
						total_deployed[function_name] += 1
				for stat_name, stat in stats.items(): # update the peak
					if stat_name != "time" and peak[stat_name] < stat:
						peak[stat_name] = stat
			while stats["time"] < total_time: # drain final requests
				if str(stats["time"]) in next_event:
					if args.scheduler == "arbiter":
						for workflow_id, shard_ids in next_event[str(stats["time"])].items():
							for shard_id in shard_ids:
								if instances[workflow_id]["shards"][shard_id]["process"] != None:
									to_delete = False
									if float(instances[workflow_id]["shards"][shard_id]["process"]["time"]) + float(instances[workflow_id]["shards"][shard_id]["process"]["latency"]) < stats["time"]: # request done, returning to idle
										mem_shard = float(instances[workflow_id]["shards"][shard_id]["process"]["mem"])
										instances[workflow_id]["allocated_total"] -= mem_shard
										instances[workflow_id]["shards"][shard_id]["allocated"] = 0 # in practice this shrinks/expands to the next stage, but its a linear trace and I am not rebuilding the topology graphs as inputs (16+GB in memory); its corrected by the search for pre-existing in the next block
										stats["used_total"] -= mem_shard
										stats["used_" + instances[workflow_id]["shards"][shard_id]["owner"]] -= mem_shard
										stats["alloc_total"] -= mem_shard
										stats["alloc_" + instances[workflow_id]["shards"][shard_id]["owner"]] -= mem_shard
										instances[workflow_id]["shards"][shard_id]["process"] = None
										no_process[workflow_id][shard_id] = 1
										if len(no_process[workflow_id]) == len(instances[workflow_id]["shards"]): # final function executed, shutting down (we know what the last function is beforehand)
											to_delete = True
									if to_delete:
										k_events["container"]["delete"][workflow_id] += 1
										del no_process[workflow_id]
										del instances[workflow_id]
					else:
						for function_name, instance_ids in next_event[str(stats["time"])].items():
							for instance_id, targets in instance_ids.items():
								for target, c in targets.items():
									if instance_id in instances[function_name]:
										if (instance_id not in no_process[function_name] or target not in no_process[function_name][instance_id]) and float(instances[function_name][instance_id]["process"][target]["time"]) + float(instances[function_name][instance_id]["process"][target]["latency"]) < stats["time"]: # request done, returning to idle
											mem_process = float(instances[function_name][instance_id]["process"][target]["mem"])
											stats["used_total"] -= mem_process
											stats["used_" + function_name] -= mem_process
											stats["idle_total"] += mem_process
											stats["idle_" + function_name] += mem_process
											if args.assignment == "exact":
												k_events["container"]["modify"][instances[function_name][instance_id]["owner"][target]] += 1
											if instances[function_name][instance_id]["owner"][target] in allocated:
												if args.assignment == "exact":
													allocated[instances[function_name][instance_id]["owner"][target]] -= mem_process
													instances[function_name][instance_id]["allocated"] -= mem_process
													stats["alloc_total"] -= mem_process
													stats["alloc_" + function_name] -= mem_process
													stats["idle_total"] -= mem_process
													stats["idle_" + function_name] -= mem_process
												if allocated[instances[function_name][instance_id]["owner"][target]] < 1:
													del allocated[instances[function_name][instance_id]["owner"][target]]
											if instance_id not in no_process[function_name]:
												no_process[function_name][instance_id] = {}
											no_process[function_name][instance_id][target] = 1
										if instances[function_name][instance_id]["last_invoked"] + args.ttl < stats["time"] and instance_id in no_process[function_name] and len(no_process[function_name][instance_id]) == args.target: # ttl reclaim
											if args.assignment == "standard":
												for t, owner in instances[function_name][instance_id]["owner"].items():
													allocated[owner] -= container_alloc[function_name] / args.target
											k_events["container"]["delete"][instances[function_name][instance_id]["owner"][target]] += 1
											mem_allocated = instances[function_name][instance_id]["allocated"]
											stats["idle_total"] -= mem_allocated
											stats["idle_" + function_name] -= mem_allocated
											stats["alloc_total"] -= mem_allocated
											stats["alloc_" + function_name] -= mem_allocated
											del instances[function_name][instance_id]
											if instance_id in no_process[function_name]:
												del no_process[function_name][instance_id]
				for stat_name, stat in stats.items(): # update the peak
					if stat_name != "time" and peak[stat_name] < stat:
						peak[stat_name] = stat
				if args.scheduler == "arbiter":
					for workflow_id, instance in instances.items(): # has not been reclaimed and needs to be "billed"
						memory_cost[workflow_id] += instance["allocated_total"]
					writer.writerow(stats) # write simulation timeline
				else:
					to_delete = []
					for workflow_id in allocated:
						if allocated[workflow_id] < 1:
							to_delete.append(workflow_id)
					for workflow_id in to_delete:
						del allocated[workflow_id]
					for workflow_id, alloc in allocated.items():
						memory_cost[workflow_id] += alloc
					writer.writerow(stats)
				stats["time"] += 1
				if stats["time"] % 1000 == 0:
					print("simulation time (ms): " + str(stats["time"]))
	with open(f'{args.folder}/{args.scheduler}-{args.assignment}-ttl_{args.ttl}-target_{args.target}-peak.csv', "w") as f:
		writer = csv.DictWriter(f, fieldnames=peak.keys())
		writer.writeheader()
		writer.writerow(peak)
	with open(f'{args.folder}/{args.scheduler}-{args.assignment}-ttl_{args.ttl}-target_{args.target}-cost.csv', "w") as f:
		writer = csv.DictWriter(f, fieldnames=memory_cost.keys())
		writer.writeheader()
		writer.writerow(memory_cost)
	with open(f'{args.folder}/{args.scheduler}-{args.assignment}-ttl_{args.ttl}-target_{args.target}-k.csv', "w") as f:
		writer = csv.DictWriter(f, fieldnames=["container_create", "container_delete", "container_modify", "cgroup_create", "cgroup_delete", "cgroup_modify"])
		writer.writeheader()
		for i in range(10000):
			row = {
				"container_create": k_events["container"]["create"][str(i)],
				"container_delete": k_events["container"]["delete"][str(i)],
				"container_modify": k_events["container"]["delete"][str(i)],
				"cgroup_create": k_events["cgroup"]["create"][str(i)],
				"cgroup_delete": k_events["cgroup"]["delete"][str(i)],
				"cgroup_modify": k_events["cgroup"]["modify"][str(i)]
			}
			writer.writerow(row)

main()
