#! /usr/bin/env python3

####################################################
#
#
# rvbench performance test
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
import sqlite3
from contextlib import closing
import numpy as np
import scipy
import xlsxwriter

from perflib import *


def find_main_fid(pd: PerfData):
    for fid, v in pd.data.items():
        if pd.get_symbol_name(fid).startswith('main:'):
            print(f'find_main_fid: {pd.get_symbol_name(fid)}')
            return fid
    print('No main() function found')
    return False


def sum_time(buckets, raw_data: list[int]) -> int:
    s = 0
    w = buckets - 1
    for c in raw_data:
        s = s + c * w
        w = w - 1
    return s


def sum_time_all(buckets, raw_data: dict[int, list[int]]) -> int:
    s = 0
    for freq in raw_data.values():
        w = buckets - 1
        for c in freq:
            s = s + c * w
            w = w - 1
    return s


def kl_div(buckets, raw_data1: list[int], raw_data2: list[int]):
    div = sum(scipy.special.rel_entr(raw_data1, raw_data2))
    return div.item()


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


def rvbench_test(pd1: PerfData, pd2: PerfData, path: str):
    """
    Compare the performance of PerfData from two platforms.
    pd1 is the collected data; pd2 is the reference data.
    """

    # find function name and matching data
    # compare using raw data
    f = open(path, 'w')
    # print(pd1.cmd)
    # f.write(f'{pd1.cmd}\n')
    f.write(f'symbol,cdf,kl_div,diff_time,data\n')

    # store data by function names
    funcs_and_data1 = {}
    for fid, data in pd1.rawData.items():
        funcs_and_data1[pd1.get_symbol_name(fid)] = data

    funcs_and_data2 = {}
    for fid, data in pd2.rawData.items():
        funcs_and_data2[pd2.get_symbol_name(fid)] = data

    total_cdf = 0
    total_diff_time = 0

    for f1, data1 in funcs_and_data1.items():
        if f1 in funcs_and_data2.keys():
            data2 = funcs_and_data2[f1]
            assert len(data1) == len(data2)
            # t1 = sum_time(pd1.buckets, data1)
            # t2 = sum_time(pd2.buckets, data2)
            score_cdf = cdf(pd1.buckets, data1, data2)
            score_kldiv = kl_div(pd1.buckets, data1, data2)
            score_diff_time = diff_time(pd1.buckets, pd1.interval, pd2.interval, data1, data2)
            total_cdf += score_cdf
            total_diff_time += score_diff_time
            # output CSV
            # TODO generate plot?
            f.write(f'{f1},{score_cdf},{score_kldiv},{score_diff_time},{','.join(map(str, data1))}\n')
            f.write(f',,,,{','.join(map(str, data2))}\n')
            

    f.write(f'total cdf,{total_cdf}\n')
    f.write(f'total diff_time,{total_diff_time}\n')
    f.close()

    # return s1, s2


def main(dir1: str, dir2: str, path: str):
    dataDir1 = dir1 + "/perf_data"
    dataDir2 = dir2 + "/perf_data"
    dbDir1   = dir1 + "/debug_info"
    dbDir2   = dir2 + "/debug_info"
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

    matches: list[tuple[PerfData, PerfData]] = find_matches(perfDatas1, perfDatas2)
    # sum scores in all matches
    sum1 = 0
    sum2 = 0
    i = 0
    for pd1, pd2 in matches:
        rvbench_test(pd1, pd2, f'{path}/{i}.csv')
        i = i + 1

    

###
### start of program
###

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='rvbench performance test')
    parser.add_argument('--dataDir1', type=str, help='directory of perf data and debuginfo from the 1st archtecture')
    parser.add_argument('--dataDir2', type=str, help='directory of perf data and debuginfo from the 2nd archtecture')
    parser.add_argument('-p', '--prefix', type=str, help='path prefix inside OBS environemnt')
    parser.add_argument('-o', '--output', type=str, help='path to store CSV')

    args = parser.parse_args()
    if args.dataDir1 == None or args.dataDir2 == None:
        print('error: the following arguments are required: --dataDir1, --dataDir2')
        exit(-1)
    if not args.prefix == None:
        set_g_obs_prefix(args.prefix)
    main(args.dataDir1, args.dataDir2, args.output)
