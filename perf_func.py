#! /usr/bin/env python3

####################################################
#
#
# cross-archtecture performance analysis tool 
#
# Author: Mao Yifu, maoif@ios.ac.cn
#
#
####################################################



import os
import sys
import struct
import argparse
# import numpy as np
# import matplotlib.pyplot as plt
# import seaborn as sns
import sqlite3
from contextlib import closing
from perflib import *

# Apply the default theme
# sns.set_theme()

# dump as text
# dump as excel?
# draw diagram


def dedup_reports(results: list[PerfResult]):
    res: dict[str, PerfResult] = {}
    for r in results:
        if r.func not in res.keys():
            res[r.func] = r

    return list(res.values())


class ReportItemNew:
    def __init__(self, func: str, fid1, fid2, code: str, file: str, plot_id: int, ratio):
        self.func = func
        self.fid1 = fid1
        self.fid2 = fid2
        self.code = code
        self.file = file
        self.plot_id = plot_id
        self.ratio = round(ratio*100, 2)


class FuncPlot:
    def __init__(self, plot_id, interval, dist1: list[int], dist2: list[int]):
        self.plot_id = plot_id
        self.interval = interval

        self.xs1= []
        self.xs2= []
        self.ys1= []
        self.ys2= []

        t = 0
        for c in dist1:
            self.ys1.append(c)
            self.xs1.append(t)
            t += 1
        t = 0
        for c in dist2:
            self.ys2.append(c)
            self.xs2.append(t)
            t += 1


def generate_report_new(results: list[PerfResult], name, path = '.'):
    results = dedup_reports(results)
    print(f'Generating report for {len(results)} results...')
    reports: ReportItemNew = []
    plots = []

    plot_id = 0
    for res in results:
        srcs, src_file = fetch_source_code(res)
        # print(res.func)
        ss = ''
        for s in srcs:
            ss += s
        reports.append(ReportItemNew(res.func, res.fid1, res.fid2, ss, src_file, plot_id, res.ratio))
        plots.append(FuncPlot(plot_id, res.pd1.interval, res.dist1, res.dist2))

        plot_id += 1

    if reports == []:
        return

    # filename = Path(reports[0].file).parts[0]
    filename = name

    from jinja2 import Environment, PackageLoader, select_autoescape
    env = Environment(
        loader=PackageLoader("perflib"),
        autoescape=select_autoescape()
    )
    template = env.get_template('report_new.html')
    with open(f'{filename}.html', 'w') as f:
        print('Rendering report...')
        f.write(template.render(perf_package = filename,
            interval = results[0].pd1.interval, buckets = results[0].pd1.buckets,
            arch1 = results[0].pd1.arch.name, arch2 = results[0].pd2.arch.name,
            reports = reports, plots = plots))
    print('Rendered.')


def main(dir1: str, dir2: str, name: str, path = '.'):
    dataDir1 = dir1 + "/perf_data"
    dataDir2 = dir2 + "/perf_data"
    dbDir1   = dir1 + "/debuginfo"
    dbDir2   = dir2 + "/debuginfo"
    srcDir1  = dir1 + "/src/"
    srcDir2  = dir2 + "/src/"

    checkDir(dataDir1)
    checkDir(dataDir1)
    checkDir(dbDir1)
    checkDir(dbDir2)
    checkDir(srcDir1)
    checkDir(srcDir2)

    # look for trec_perf_*

    files1 = os.listdir(dataDir1)
    files2 = os.listdir(dataDir2)
    # name must be aligned with that in perfRT
    isPerfData = lambda x: x.startswith('trec_perf_')
    joinDatDir = lambda dir: lambda x: os.path.join(dir, x)
    perfDataFiles1 = list(map(joinDatDir(dataDir1), filter(isPerfData, files1)))
    perfDataFiles2 = list(map(joinDatDir(dataDir2), filter(isPerfData, files2)))

    if perfDataFiles1 == []:
        print(f"{dataDir1} has no data files")
        exit(0)
    if perfDataFiles1 == []:
        print(f"{dataDir2} has no data files")
        exit(0)

    perfDatas1 = list(map(read_perf_data, perfDataFiles1))
    perfDatas2 = list(map(read_perf_data, perfDataFiles2))

    for pd in perfDatas1:
        pd.dbDir = dbDir1
        pd.srcDir = srcDir1

    for pd in perfDatas2:
        pd.dbDir = dbDir2
        pd.srcDir = srcDir2

    res, good_res = analyze_all(perfDatas1, perfDatas2)
    generate_report_new(res, name, path)


###
### start of program
###

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Analyze program performance across architectures.')
    parser.add_argument('dataDir1', type=str, help='directory of perf data and debuginfo from the 1st archtecture')
    parser.add_argument('dataDir2', type=str, help='directory of perf data and debuginfo from the 2nd archtecture')
    parser.add_argument('-p', '--prefix', type=str, help='path prefix inside OBS environemnt')
    parser.add_argument('-t', '--threshold', type=float, help='bad performance threshold, default: 0.8')
    parser.add_argument('-n', '--name', type=str, help='name of package')
    parser.add_argument('-o', '--output', type=str, help='path to report')

    args = parser.parse_args()
    if not args.prefix == None:
        set_g_obs_prefix(args.prefix)
    if not args.threshold == None:
        set_g_bad_threshold(args.threshold)
    if args.name == None:
        name = 'unknown_package'
    else:
        name = args.name
    if args.output == None:
        path = '.'
    else:
        path = args.output
    main(args.dataDir1, args.dataDir2, name, path)