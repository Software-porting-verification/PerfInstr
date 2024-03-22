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

# Apply the default theme
# sns.set_theme()

# dump as text
# dump as excel?
# draw diagram


class PerfData:
    # dict[fid, list[counts]]
    rawData: dict[int, list[int]] 
    # dict[fid, dict[interval, counts]]
    data: dict[int, dict[int, int]]
    mode: int
    numOfFuncs: int


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


    def getExeParams(self):
        return self.cmd + self.exe + self.pwd


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



def decodeFid(fid):
    dbID   = (fid >> 48) & 0xffff
    fileID = (fid >> 24) & 0xffffff
    funcID = fid & 0xffffff

    return dbID, funcID, fileID


def checkDB(path):
    if os.path.exists(path):
        if not os.path.isfile(path):
            print(f"Not a database file: {path}")
            exit(-1)
    else:
        print(f"Database file not found: {path}")
        exit(-1)


def queryFuncName(fid, debuginfo_dir):
    dbID, funcID, _ = decodeFid(fid)
    dbName = f"{debuginfo_dir}/debuginfo{dbID}.db"
    if dbID < 0:
        print(f"Less than 0: {dbID}")
    checkDB(dbName)
    with closing(sqlite3.connect(dbName)) as connection:
        with closing(connection.cursor()) as cursor:
            rows = cursor.execute("select NAME from FUNCNAMES where ID=?", (funcID,)).fetchall()
            return rows[0][0]


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
        # print(f"mode: {mode}, bucket length: {length}")

        # TODO flexible interval size
        perfData = PerfData(data_path, cmd, exe, pwd, 5000)
        perfData.mode = mode
        perfData.numOfFuncs = length

        # read each function's counts
        len_fid_buckets = (length + 1) * 8
        num_func  = (len(bs) - (1 + 4)) // len_fid_buckets
        # print(f"Number of functions: {num_func}")

        # data : fid -> bucket
        data = {}
        start = i + 5
        for i in range(num_func):
            fid = struct.unpack('<Q', bs[start:start + 8])[0]
            start += 8
            vec = []
            for bucket_i in range(length):
                vec.append(struct.unpack('<q', bs[start:start + 8])[0])
                start += 8

            perfData.addRawData(fid, vec)
        
        return perfData


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

###
### start of program
###

parser = argparse.ArgumentParser(
    prog='perf-analyzer',
    description='Analyze program performance across architectures.')
parser.add_argument('dataDir1', type=str, help='directory of perf data and debuginfo from the 1st archtecture')
parser.add_argument('dataDir2', type=str, help='directory of perf data and debuginfo from the 2nd archtecture')

args = parser.parse_args()

# find matching data for analysis

dataDir1 = args.dataDir1 + "/perf_data"
dataDir2 = args.dataDir2 + "/perf_data"
dbDir1   = args.dataDir1 + "/debuginfo"
dbDir2   = args.dataDir2 + "/debuginfo"

checkDir(dataDir1)
checkDir(dataDir1)
checkDir(dbDir1)
checkDir(dbDir2)

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

# start to find matches

list1 = perfDatas1.copy()
list2 = perfDatas2.copy()

matches: list[tuple[PerfData, PerfData]] = []
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
    

for kv in matches:
    print(f"1st: {kv[0].cmd}")
    print(f"2nd: {kv[1].cmd}")
    print()