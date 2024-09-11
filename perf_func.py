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


def outputDiagram():
    pass


def outputExcel():
    pass


def outputText(data, interval):
    pass


def main(dir1: str, dir2: str):
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
    generate_report(res)


###
### start of program
###

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='perf-instr',
        description='Analyze program performance across architectures.')
    parser.add_argument('dataDir1', type=str, help='directory of perf data and debuginfo from the 1st archtecture')
    parser.add_argument('dataDir2', type=str, help='directory of perf data and debuginfo from the 2nd archtecture')
    parser.add_argument('-p', '--prefix', type=str, help='path prefix inside OBS environemnt')

    args = parser.parse_args()
    if not args.prefix == None:
        set_g_obs_prefix(args.prefix)