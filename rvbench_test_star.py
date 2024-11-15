#! /usr/bin/env python3

####################################################
#
#
# Compute the sum and average performance scores from the list of performance data of the same set of programs.
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
import numpy as np
import scipy
import xlsxwriter

from perflib import *


def sum_time(buckets, raw_data: list[int]) -> int:
    w = np.array([i for i in range(buckets-1, -1, -1)])
    d = np.array(raw_data)
    # print(w)
    # print(d)
    s = (w * d).sum().item()

    return s


def sum_time_all(buckets, raw_data: dict[int, list[int]]) -> int:
    s = 0
    for freq in raw_data.values():
        w = buckets - 1
        for c in freq:
            s = s + c * w
            w = w - 1
    return s


def cdf(buckets, raw_data1: list[int], raw_data2: list[int]):
    weights = np.array([i for i in range(buckets-1, -1, -1)])
    d1 = np.array(raw_data1)
    d2 = np.array(raw_data2)
    # bigger positive s means arch1 is faster than arch2
    s = ((d1 - d2) * weights).sum().item()

    return s


def diff_time(buckets, interval1, interval2, raw_data1: list[int], raw_data2: list[int]):
    interv1 = np.array([i for i in range(0, buckets * interval1, interval1)])
    interv2 = np.array([i for i in range(0, buckets * interval2, interval2)])
    d1 = np.array(raw_data1)
    d2 = np.array(raw_data2)

    # bigger positive s means arch1 is faster than arch2
    s = np.sum(interv2 * d2) - np.sum(interv1 * d1)
    return s.item()


def compute_score(pd, fid, func_name, data):
    return sum_time(pd.buckets, data)


def sum_data(data_list: list[list[int]]):
    summed_data = np.zeros(len(data_list[0]))
    for d in data_list:
        summed_data += np.array(d)

    return summed_data


def rvbench_test_star(pds: list[PerfData], path):
    """
    Compute the sum and average performance scores from the list of performance data.
    The list of data should come from the same set of programs.
    """

    # find function name and matching data
    # compare using raw data
    f = open(path, 'w')
    f.write(f'cmd: {pds[0].cmd}\n')
    f.write(f'symbol,score_total,score_avg,')
    i = 1
    for pd in pds:
        f.write(f'score {i},')
        i += 1
    f.write('data\n')

    # get common fid
    lists_of_pd_fid_func_data: list[list[tuple[PerfData,int,str,list[int]]]] = \
        list(map(lambda pd: list(map(lambda kv: (pd, kv[0], pd.get_symbol_name(kv[0]), kv[1]), pd.rawData.items())), pds))
    sets_of_funcs: list[set[int]] = \
        list(map(lambda pd: set(map(lambda fid: pd.get_symbol_name(fid), pd.rawData.keys())), pds))

    common_funcs = sets_of_funcs[0]
    for s in sets_of_funcs[1:]:
        common_funcs = s & common_funcs

    # compute func -> list[(fid, func, raw_data)] map
    func_to_list_of_data = {}
    for func in common_funcs:
        matching_data: list[tuple[PerfData,int,str,list[int]]] = []
        for pd_fid_func_data_list in lists_of_pd_fid_func_data:
            for pd, fid, func_name, data in pd_fid_func_data_list:
                if func == func_name:
                    matching_data.append((pd,fid,func_name,data))
                    break

        func_to_list_of_data[func] = matching_data
        assert len(matching_data) == len(pds)

    for func, matching_data_list in func_to_list_of_data.items():
        result_list = list(map(lambda x: compute_score(x[0], x[1], x[2], x[3]), matching_data_list))
        s = sum(result_list)
        avg = s / len(result_list)

        # add up dist
        summed_data = sum_data(list(map(lambda x: x[3], matching_data_list))).tolist()

        f.write(f'{func},{s},{avg},')
        for r in result_list:
            f.write(f'{r},')
        f.write(f'{','.join(map(str, summed_data))}\n')

    f.close()



def main(dirs: list[str], path: str):
    def read_one_dir(p: str):
        print(f'Reading data under {p}')

        dataDir = p + "/perf_data"
        dbDir   = p + "/debuginfo"
        srcDir  = p + "/src/"

        checkDir(dataDir)
        checkDir(dbDir)
        checkDir(srcDir)

        # look for trec_perf_*
        files = os.listdir(dataDir)
        # name must be aligned with that in perfRT
        isPerfData = lambda x: x.startswith('trec_perf_')
        joinDatDir = lambda dir: lambda x: os.path.join(dir, x)
        perfDataFiles = list(map(joinDatDir(dataDir), filter(isPerfData, files)))

        if perfDataFiles == []:
            print(f"{dataDir} has no data files")
            exit(0)

        perfDatas = list(map(read_perf_data, perfDataFiles))

        for pd in perfDatas:
            pd.dbDir = dbDir
            pd.srcDir = srcDir

        return perfDatas

    perf_data_list_list: list[list[PerfData]] = list(map(read_one_dir, dirs))
    matches: list[list[PerfData]] = find_matches_star(perf_data_list_list)

    print('Computing score...')
    i = 0
    for ms in matches:
        rvbench_test_star(ms, f'{path}/{i}.csv')
        i += 1

    print('Done.')
    

###
### start of program
###

# Generate the sum total of several perf data sets.

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Compute the sum and average performance scores from the list of performance data of the same set of programs.')
    parser.add_argument('-o', '--output', type=str, help='path to store CSV')
    parser.add_argument('dataDirs', nargs='+', type=str, help='directories of perf data and debuginfo')

    args = parser.parse_args()
    main(args.dataDirs, args.output)
