import numpy as np
import csv
from pathlib import Path

stats = {
	"entry": {"latency_mu": 1, "latency_sigma": 0, "mem_mu": 1, "mem_sigma": 0, "count": 1},
	"fastqSplit": {"latency_mu": 60, "latency_sigma": 10, "mem_mu": 100, "mem_sigma": 10, "count": 2},
	"filterContams": {"latency_mu": 20, "latency_sigma": 3, "mem_mu": 65, "mem_sigma": 8, "count": 500},
	"sol2sanger": {"latency_mu": 80, "latency_sigma": 5, "mem_mu": 45, "mem_sigma": 8, "count": 500},
	"fast2bfq": {"latency_mu": 45, "latency_sigma": 7, "mem_mu": 80, "mem_sigma": 7, "count": 500},
	"map": {"latency_mu": 10000, "latency_sigma": 500, "mem_mu": 185, "mem_sigma": 5, "count": 500},
	"mapMerge1": {"latency_mu": 120, "latency_sigma": 20, "mem_mu": 120, "mem_sigma": 10, "count": 2},
	"mapMerge2": {"latency_mu": 120, "latency_sigma": 20, "mem_mu": 120, "mem_sigma": 10, "count": 1},
	"chr21": {"latency_mu": 150, "latency_sigma": 30, "mem_mu": 55, "mem_sigma": 7, "count": 1},
	"pileup": {"latency_mu": 180, "latency_sigma": 45, "mem_mu": 95, "mem_sigma": 12, "count": 1}
}

headers = ["request", "latency", "mem"]

def main():
	Path("../trace/requests").mkdir(parents=True, exist_ok=True)
	for i in range(10000):
		with open(f'../trace/requests/epigenomics-{i}.csv', "w") as f:
			requests = []
			for func in stats.keys():
				latency = np.random.normal(stats[func]["latency_mu"], stats[func]["latency_sigma"], stats[func]["count"])
				mem = np.random.normal(stats[func]["mem_mu"], stats[func]["mem_sigma"], stats[func]["count"])
				for j in range(stats[func]["count"]):
					if latency[j] <= 0 or mem[j] <= 0:
						print("invalid latency or mem: " + func)
					requests.append({"request": f'epigenomics_{i}_{func}_{j}', "latency": latency[j], "mem": mem[j]})
			writer = csv.DictWriter(f, fieldnames=headers)
			writer.writeheader()
			writer.writerows(requests)

main()
