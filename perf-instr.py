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


def readData(data_path: str) -> PerfData:
    with open(data_path, mode='rb') as file:
        bs = file.read()
        # cmdline
        rawCmd = []
        i = 0
        while not bs[i] == 3:
            c = struct.unpack('<c', bs[i:i+1])[0]
            # note that '\0' exists
            rawCmd.append(c.decode('utf-8'))
            i += 1
        i += 1
        # exe path
        rawExe = []
        while not bs[i] == 3:
            # print(i)
            c = struct.unpack('<c', bs[i:i+1])[0]
            rawExe.append(c.decode('utf-8'))
            i += 1
        i += 1
        # working dir
        rawPwd = []
        while not bs[i] == 3:
            # print(i)
            c = struct.unpack('<c', bs[i:i+1])[0]
            rawPwd.append(c.decode('utf-8'))
            i += 1
        i += 1

        cmd = "".join(rawCmd)
        exe = "".join(rawExe)
        pwd = "".join(rawPwd)
        exeParams = cmd + exe + pwd
        # print(f"cmd: {cmd}, exe: {exe}, pwd: {pwd}")
        # print(f"exeParams: {exeParams}")

        # <: little endian
        mode   = struct.unpack('<b', bs[i   : i+1])[0]
        length = struct.unpack('<i', bs[i+1 : i+5])[0]
        interval = struct.unpack('<i', bs[i+5 : i+9])[0]
        # print(f"mode: {mode}, bucket length: {length}")

        perfData = PerfData(data_path, cmd, exe, pwd, interval)
        perfData.mode = mode
        perfData.numOfFuncs = length

        # read each function's counts
        len_fid_buckets = (length + 1) * 8
        num_func  = (len(bs) - (1 + 4)) // len_fid_buckets
        # print(f"Number of functions: {num_func}")

        # data : fid -> bucket
        data = {}
        start = i + 9
        for i in range(num_func):
            fid = struct.unpack('<Q', bs[start:start + 8])[0]
            start += 8
            vec = []
            for bucket_i in range(length):
                vec.append(struct.unpack('<q', bs[start:start + 8])[0])
                start += 8

            perfData.addRawData(fid, vec)
        
        return perfData


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

    perfDatas1 = list(map(readData, perfDataFiles1))
    perfDatas2 = list(map(readData, perfDataFiles2))

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
    main(args.dataDir1, args.dataDir2)