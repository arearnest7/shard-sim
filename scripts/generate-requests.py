import numpy as np
import csv
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(prog="python3 simulate.py")
parser.add_argument("--folder_out", default="../trace/requests/")
parser.add_argument("--wf_jobs", default=100, type=int)

# latency in ms
# mem in MB

stats = {
	"entry": {"latency_mu": 1, "latency_sigma": 0, "mem_mu": 1, "mem_sigma": 0, "count": 1},
	"fastqSplit": {"latency_mu": 34320, "latency_sigma": 8940, "mem_mu": 2.8, "mem_sigma": 0, "count": 2},
	"filterContams": {"latency_mu": 2470, "latency_sigma": 430, "mem_mu": 2.97, "mem_sigma": 0.06, "count": 500},
	"sol2sanger": {"latency_mu": 480, "latency_sigma": 140, "mem_mu": 3.79, "mem_sigma": 0, "count": 500},
	"fast2bfq": {"latency_mu": 1400, "latency_sigma": 240, "mem_mu": 4.05, "mem_sigma": 0.01, "count": 500},
	"map": {"latency_mu": 201890, "latency_sigma": 21910, "mem_mu": 196.04, "mem_sigma": 5.5, "count": 500},
	"mapMerge1": {"latency_mu": 11010, "latency_sigma": 12180, "mem_mu": 5, "mem_sigma": 0.39, "count": 2},
	"mapMerge2": {"latency_mu": 11010, "latency_sigma": 12180, "mem_mu": 5, "mem_sigma": 0.39, "count": 1},
	"chr21": {"latency_mu": 43570, "latency_sigma": 0, "mem_mu": 6.17, "mem_sigma": 0, "count": 1},
	"pileup": {"latency_mu": 55950, "latency_sigma": 0, "mem_mu": 148.26, "mem_sigma": 0, "count": 1}
}

headers = ["request", "latency", "mem"]

def main():
	args = parser.parse_args()
	Path(args.folder_out).mkdir(parents=True, exist_ok=True)
	for i in range(args.wf_jobs):
		with open(f'{args.folder_out}/epigenomics-{i}.csv', "w") as f:
			requests = []
			for func in stats.keys():
				latency = np.random.normal(stats[func]["latency_mu"], stats[func]["latency_sigma"], stats[func]["count"])
				mem = np.random.normal(stats[func]["mem_mu"], stats[func]["mem_sigma"], stats[func]["count"])
				for j in range(stats[func]["count"]):
					if mem[j] <= 0:
						print("invalid latency mem: " + func)
					if latency[j] <= 0: # invalid latency, setting to average
						latency[j] = stats[func]["latency_mu"]
					requests.append({"request": f'epigenomics_{i}_{func}_{j}', "latency": latency[j], "mem": mem[j]})
			writer = csv.DictWriter(f, fieldnames=headers)
			writer.writeheader()
			writer.writerows(requests)

main()
