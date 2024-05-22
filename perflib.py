####################################################
#
#
# common code for performance analysis
#
# Author: Mao Yifu, maoif@ios.ac.cn
#         Zhou ZhiYang
#
####################################################


import shutil
import os
import subprocess
import yaml
import argparse
import sqlite3
from contextlib import closing


class PerfData:
    # dict[fid, list[counts]]
    rawData: dict[int, list[int]]
    # dict[fid, dict[interval, counts]]
    data: dict[int, dict[int, int]]
    # 0: time, 1: cycle, 2: insn, 3: perf
    mode: int
    numOfFuncs: int
    dbDir: str = None
    symbol_dict: dict[int, str] = None


    def __init__(self, dataPath: str, cmd: str, exe: str, pwd: str, interval: int):
        # path of this data file
        self.dataPath = dataPath
        # cmdline and arguments
        self.cmd = cmd
        # path of the testcase executable
        self.exe = exe
        # path the the testcase's working directory
        self.pwd = pwd
        # time interval on the frequency vector
        self.interval = interval
        self.rawData = {}
        self.data = {}

    
    def addRawData(self, fid, vec):
        """
        Add raw frequency vector for a function and make a dict
        for frequency values > 0.
        """
        times = {}
        start = 0
        for c in vec:
            if c > 0:
                times[start] = c
                start += self.interval
        self.rawData[fid] = vec
        self.data[fid] = times


    def get_symbol_name(self, sid):
        """
        If mode is 3, use `symbol_dict`,
        otherwise, use `dbDir`.
        """
        if self.mode == 3:
            return self.symbol_dict[sid]
        else:
            dbID, funcID, _ = decodeFid(sid)
            dbName = f"{self.dbDir}/debuginfo{dbID}.db"
            if dbID < 0:
                print(f"Less than 0: {dbID}")
            checkDB(dbName)
            with closing(sqlite3.connect(dbName)) as connection:
                with closing(connection.cursor()) as cursor:
                    rows = cursor.execute("select NAME from FUNCNAMES where ID=?", (funcID,)).fetchall()
                    return rows[0][0]


def decodeFid(fid):
    dbID   = (fid >> 48) & 0xffff
    fileID = (fid >> 24) & 0xffffff
    funcID = fid & 0xffffff

    return dbID, funcID, fileID


def queryFileName(fid, debuginfo_dir):
    dbID, _, fileID = decodeFid(fid)
    dbName = f"{debuginfo_dir}/debuginfo{dbID}.db"
    if dbID < 0:
        print(f"Less than 0: {dbID}")
    checkDB(dbName)
    with closing(sqlite3.connect(dbName)) as connection:
        with closing(connection.cursor()) as cursor:
            rows = cursor.execute("select NAME from FILENAMES where ID=?", (fileID,)).fetchall()
            return rows[0][0]


def checkDir(path: str):
    if os.path.exists(path):
        if not os.path.isdir(path):
            print(f"Not a dir: {path}")
            exit(-3)
        
        if os.listdir(path) == []:
            print(f"Dir {path} is empty")
            exit(-3)
    else:
        print(f"Dir not found: {path}")
        exit(-4)


def checkFile(path: str):
    if os.path.exists(path):
        if not os.path.isfile(path):
            print(f"Not a file: {path}")
            exit(-3)
    else:
        print(f"Dir not found: {path}")
        exit(-4)


def checkDB(path):
    if os.path.exists(path):
        if not os.path.isfile(path):
            print(f"Not a database file: {path}")
            exit(-1)
    else:
        print(f"Database file not found: {path}")
        exit(-1)


def find_matches(perfDatas1: list[PerfData], perfDatas2: list[PerfData]) -> list[tuple[PerfData, PerfData]]:
    list1 = perfDatas1.copy()
    list2 = perfDatas2.copy()

    # matches: list[tuple[PerfData, PerfData]] = []
    matches = []
    i = 0
    while True:
        if i == len(list1):
            # by now all pairs have been compared
            break

        pd1 = list1[i]
        foundMatch = False
        for pd2 in list2:
            if pd1.cmd == pd2.cmd:
                matches.append((pd1, pd2))
                list1.remove(pd1)
                list2.remove(pd2)
                foundMatch = True
                break
        
        # pd1 has no matching pd2, go to the next
        if not foundMatch:
            i += 1

    return matches


import numpy as np
from scipy.stats import ttest_ind, mannwhitneyu, ks_2samp, chisquare
from sklearn import preprocessing
from scipy import stats


def standardlization(arr1):
    arr1_np=np.array(arr1)
    return (arr1_np-arr1_np.min())/(arr1_np.max()-arr1_np.min())


def analyze(pd1: PerfData, pd2: PerfData):
    # print('cmd:', pd1.cmd)
    pd1_data = {}
    pd2_data = {}
    paired_data1 = {}
    paired_data2 = {}
    # print(pd1.data)
    
    for fid in pd1.data.keys():
        if len(pd1.data[fid])<=1:
            continue
        func = pd1.get_symbol_name(fid)
        pd1_data[func] = pd1.data[fid]
        
    for fid in pd2.data.keys():
        if len(pd2.data[fid])<=1:
            continue
        func = pd2.get_symbol_name(fid)
        #pd2_data[func] = [fid, pd2.data[fid]]
        pd2_data[func] = pd2.data[fid]
    
    for func in pd1_data.keys():
        if func in pd2_data:
            times1=[]
            # k: left time interval, i.e., [k, k')
            # v: number of times
            # duplicate each k, v times
            for k,v in pd1_data[func].items():
                times1+=[k for i in range(0,v)]
            times1=standardlization(times1)
            paired_data1[func] = times1
            
            times2=[]
            for k,v in pd2_data[func].items():
                times2+=[k for i in range(0,v)]
            times2=standardlization(times2)
            paired_data2[func] = times2
            
    for func in paired_data1.keys():
        if func in paired_data2:
            income_t=paired_data1[func]
            income_c=paired_data2[func]
            # statistics, pvalues = ttest_ind(income_t,income_c)
            # statistics, pvalues = mannwhitneyu(income_t,income_c)
            # statistics, pvalues = chisquare(income_t,income_c)
            statistics, pvalues = ks_2samp(income_t,income_c)
            if pvalues < statistics:
                print(f'Function: {func}')
                print('WARNING, statistics > pvalues({} > {})'.format(statistics, pvalues))
            else:
                print('INFO, statistics <= pvalues({} <= {})'.format(statistics, pvalues))
            # print('func:', func, 'times in pd1:', list(income_t), 'times in pd2:', list(income_c))
