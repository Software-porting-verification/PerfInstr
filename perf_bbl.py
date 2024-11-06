#! /usr/bin/env python3

####################################################
#
#
# cross-archtecture performance analysis tool using BBL data.
#
# Author: Mao Yifu, maoif@ios.ac.cn
#
#
####################################################



import os
import sys
import struct
import argparse
import sqlite3
from contextlib import closing
from collections import defaultdict
import tempfile
from base64 import b64encode

from perflib import *


class BBLResult():
    def __init__(self, pd, fid, func, dist1, dist2, linestart, lineend):
        # use perf_data and fid to fetch source
        self.perf_data  = pd
        self.fid  = fid
        self.func = func
        self.dist1 = dist1
        self.dist2 = dist2
        self.linestart = linestart
        self.lineend = lineend


# a function name in the sidebar
class Func:
    def __init__(self, name, tab_id):
        self.name = name
        self.tab_id = tab_id


# a dropdown testcase+funcs in the sidebar
class Testcase:
    def __init__(self, id, cmd, funcs: list[Func]):
        self.id = id
        self.cmd = cmd
        self.funcs = funcs


# each plot+src in the report
class BBLRep:
    def __init__(self, num, plot_id, src):
        self.num = num
        self.plot_id = plot_id
        self.src = src


class Tab:
    def __init__(self, tab_id, testcase, func_name):
        self.tab_id = tab_id
        self.testcase = testcase
        self.func_name = func_name
        self.reports: list[BBLRep] = []


class BBLPlot:
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


def generate_bbl_report(results: list[list[BBLResult]], path = '.'):
    print(f'Generating report for {len(results)} testcases...')
    # sublists in `results` are per-testcase/PerfData
    testcases = []
    tabs = []
    plots = []
    package_name = None

    tc_id = 0
    tab_id = 0
    plot_id = 0
    for bbl_res in results:
        if bbl_res == []:
            continue
        testcase_name = bbl_res[0].perf_data.cmd
        # group BBL result by function; used to generate dropdown and tab
        res_by_func = defaultdict(list)
        for res in bbl_res:
            res_by_func[res.func].append(res)
        
        funcs = []
        for func_name, res_list in res_by_func.items():
            rep_func = Func(func_name, tab_id)
            rep_tab = Tab(tab_id, testcase_name, func_name)

            funcs.append(rep_func)
            tabs.append(rep_tab)

            tab_id += 1

            bbl_num = 0
            for res in res_list:
                # make per-tab reports
                src, file = fetch_source_code_range(res.perf_data, func_name, res.fid, res.linestart, res.lineend)
                if package_name is None:
                    package_name = Path(file).parts[0]

                bbl_rep = BBLRep(bbl_num, plot_id, ''.join(src))
                bbl_plot = BBLPlot(plot_id, res.perf_data.interval, res.dist1, res.dist2)

                rep_tab.reports.append(bbl_rep)
                plots.append(bbl_plot)

                bbl_num += 1
                plot_id += 1

        tc = Testcase(tc_id, testcase_name, funcs)
        testcases.append(tc)
        tc_id += 1

    from jinja2 import Environment, PackageLoader, select_autoescape
    env = Environment(
        loader=PackageLoader("perf_bbl"),
        autoescape=select_autoescape()
    )

    template = env.get_template('bbl_report.html')
    with open(f'{package_name}.html', 'w') as f:
        print('Rendering BBL report...')
        f.write(template.render(package_name = package_name, 
                                testcases = testcases,
                                tabs = tabs,
                                plots = plots))
    print('Rendered.')


def analyze_bbls(pd1: PerfData, pd2: PerfData):
    # {func1: [data1, data2, ...], ...}
    func_data_1 = defaultdict(list)
    func_data_2 = defaultdict(list)

    # find func names from bblid
    for bblid, data in pd1.data.items():
        fn = pd1.get_symbol_name(bblid)
        fid = pd1.get_bbl_fid(bblid)
        # print(f'bblid: {bblid}, funcname: {fn}')
        func_data_1[fn].append((fid, bblid, data, pd1.rawData[bblid]))

    for bblid, data in pd2.data.items():
        fn = pd2.get_symbol_name(bblid)
        fid = pd2.get_bbl_fid(bblid)
        # print(f'bblid: {bblid}, funcname: {fn}')
        func_data_2[fn].append((fid, bblid, data, pd2.rawData[bblid]))
    
    good = []
    bad  = []
    # find matching functions and their bbls
    for f1, ds1 in func_data_1.items():
        if f1 in func_data_2.keys():
            ds2 = func_data_2[f1]
            # ds1, ds2: [(fid, bblid, data), ...]
            workQ = []
            for fid1, bblid1, d1, raw_d1 in ds1:
                # pair BBLs using start/end line
                s1, e1 = pd1.get_bbl_lines(bblid1)
                for fid2, bblid2, d2, raw_d2 in ds2:
                    s2, e2 = pd2.get_bbl_lines(bblid2)
                    if s1 == s2 and e1 == e2:
                        workQ.append((f1, d1, d2, s1, e1, fid1, fid2, raw_d1, raw_d2))

            # print(f'workQ size: {len(workQ)}')
            # do the analysis
            for func, d1, d2, s, e, fid1, fid2, raw_d1, raw_d2 in workQ:
                # is_good, dist1, dist2 = analyze_data(d1, d2)
                is_good, r = compare_time(pd1.buckets, pd1.interval, raw_d1, pd2.interval, raw_d2)
                if is_good:
                    # use pd1 as key for later per-testcase report generation
                    good.append(BBLResult(pd1, fid1, func, raw_d1, raw_d2, s, e))
                else:
                    bad.append(BBLResult(pd1, fid1, func, raw_d1, raw_d2, s, e))

    # print(f'Good results: {len(good)}')
    # print(f'Bad results:  {len(bad)}')

    return good, bad


def bbl_analyze_all(perfDatas1: list[PerfData], perfDatas2: list[PerfData]):
    print('Preparing to analyze...')

    matches: list[tuple[PerfData, PerfData]] = find_matches(perfDatas1, perfDatas2)
    print(f'Found {len(matches)} matching testcases.')
    if matches == []:
        print('No match found')
        exit(0)

    print('Analyzing...')

    goods: list[list[BBLResult]] = []
    bads:  list[list[BBLResult]] = []
    for kv in matches:
        # results per perf.data/test program
        good, bad = analyze_bbls(kv[0], kv[1])
        goods.append(good)
        bads.append(bad)

    print('Done.')
    return bads


def main(dir1: str, dir2: str):
    dataDir1 = dir1 + "/perf_data_bbl_0"
    dataDir2 = dir2 + "/perf_data_bbl_1"
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
        if not pd.mode == 4:
            print(f'Perf data file mode is {pd.mode}, which is not BBL mode.')
            exit(-1)
        pd.dbDir = dbDir1
        pd.srcDir = srcDir1

    for pd in perfDatas2:
        if not pd.mode == 4:
            print(f'Perf data file mode is {pd.mode}, which is not BBL mode.')
            exit(-1)
        pd.dbDir = dbDir2
        pd.srcDir = srcDir2

    res = bbl_analyze_all(perfDatas1, perfDatas2)
    generate_bbl_report(res)


###
### start of program
###

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Analyze program performance across architectures using BBL data.')
    parser.add_argument('dataDir1', type=str, help='directory of perf data and debuginfo from the 1st archtecture')
    parser.add_argument('dataDir2', type=str, help='directory of perf data and debuginfo from the 2nd archtecture')
    parser.add_argument('-p', '--prefix', type=str, help='path prefix inside OBS environemnt')

    args = parser.parse_args()
    if not args.prefix == None:
        set_g_obs_prefix(args.prefix)
    main(args.dataDir1, args.dataDir2)