#! /bin/python

import os
import sys
import struct
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

def readData(data_path):
    with open(data_path, mode='rb') as file:
        bs = file.read()
        # <: little endian
        mode   = struct.unpack('<b', bs[0:1])[0]
        length = struct.unpack('<i', bs[1:5])[0]
        # TODO interval size
        print(f"mode: {mode}, bucket length: {length}")

        # read each function's counts
        len_fid_buckets = (length + 1) * 8
        num_func  = (len(bs) - (1 + 4)) // len_fid_buckets
        print(f"Number of functions: {num_func}")

        data = {}
        start = 5
        for i in range(num_func):
            fid = struct.unpack('<Q', bs[start:start + 8])[0]
            start += 8
            buckets = []
            for bucket_i in range(length):
                buckets.append(struct.unpack('<q', bs[start:start + 8])[0])
                start += 8

            data[fid] = buckets

        return data

# add time interval
def cleanseData(data, interval):
    res = {}
    for k, v in data.items():
        times = {}
        start = 0
        for c in v:
            if c > 0:
                times[start] = c
            
            start += interval

        res[k] = times

    return res

args = sys.argv

if len(args) < 4:
    print(f"Invalid number of arguments: {args}")
    print("Args: <mode> <debuginfo/path> <data_file>")
    print("      <mode> := txt | pic | xls")
    exit(-1)

mode = args[1]
debuginfo_dir = args[2]
data_path = args[3]
# TODO database path

if mode not in ["txt", "pic", "xls"]:
    print(f"Invalid command: {mode}")
    exit(-2)

if os.path.exists(debuginfo_dir):
    if not os.path.isdir(debuginfo_dir):
        print(f"Not a file: {debuginfo_dir}")
        exit(-3)
else:
    print(f"Dir not found: {debuginfo_dir}")
    exit(-4)

if os.path.exists(data_path):
    if not os.path.isfile(data_path):
        print(f"Not a file: {data_path}")
        exit(-3)
else:
    print(f"File not found: {data_path}")
    exit(-4)

# TODO more flexible interval
interval = 5000
data = cleanseData(readData(data_path), interval)

for k, v in data.items():
    print(f"fid: {k} {decodeFid(k)}")
    print(f"function: {queryFuncName(k, debuginfo_dir)}\nfile: {queryFileName(k, debuginfo_dir)}")
    for t, c in v.items():
        print(f"\t{t} - {t + interval}: {c}")

