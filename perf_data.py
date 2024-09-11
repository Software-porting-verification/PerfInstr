#! /usr/bin/env python3

####################################################
#
#
# morph perf data in sqlite to that of perfRT
#
# Author: Mao Yifu, maoif@ios.ac.cn
#
#
####################################################

import shutil
import os
import subprocess
import yaml
import argparse
import sqlite3
from contextlib import closing
from perflib import *


g_interval = 5000


class Sample:
    def __init__(self, id, comm_id, dso_id, symbol_id, ip, time, callpath_id):
        self.id = id
        self.comm_id = comm_id
        self.dso_id = dso_id
        self.symbol_id = symbol_id
        self.ip = ip
        # nanosecond
        self.time = time
        self.callpath_id = callpath_id


class CallPath:
    def __init__(self, id, parent_id, symbol_id):
        self.id = id
        self.parent_id = parent_id
        self.symbol_id = symbol_id


def find_cmdline(db: str, raws: list[str]) -> str:
    n = os.path.basename(db).rstrip('.db')
    for r in raws:
        if n in r:
            with open(r, 'r') as f:
                while True:
                    line = f.readline()
                    if not line:
                        print(f'Error reading cmdline from {r}')
                        exit(-1)
                    else:
                        if '# cmdline :' in line:
                            return line


def resolve_callchain(sample: Sample, symbols: dict[int, str], callpaths: dict[int, CallPath]) -> tuple[Sample, list[int]]:
    # TODO what if this symbol is unknown?
    sym_id = sample.symbol_id
    callpath_id = sample.callpath_id
    res = [sym_id]

    cc = callpaths[callpath_id]
    while True:
        if cc.parent_id == 0:
            break
        
        sid = cc.symbol_id
        # ignore unknown symbol names
        if not symbols[sid] == 'unknown':
            res.append(sid)

        cc = callpaths[cc.parent_id]

    return (sample, res)


def read_samples(db: str) -> list[Sample]:
    with closing(sqlite3.connect(db)) as connection:
        with closing(connection.cursor()) as cursor:
            rows = cursor.execute("select id,comm_id,dso_id,symbol_id,ip,time,call_path_id from samples").fetchall()
            # drop the 1st zero row
            res = []
            for i in rows:
                res.append(Sample(i[0], i[1], i[2], i[3], i[4], i[5], i[6]))
            return res


def read_symbols(db: str):
    with closing(sqlite3.connect(db)) as connection:
        with closing(connection.cursor()) as cursor:
            rows = cursor.execute("select id,name from symbols").fetchall()
            res = {}
            for i in rows:
                res[i[0]] = i[1]
            return res


def read_callpaths(db: str) -> dict[int, CallPath]:
    with closing(sqlite3.connect(db)) as connection:
        with closing(connection.cursor()) as cursor:
            rows = cursor.execute("select id,parent_id,symbol_id from call_paths").fetchall()
            res = {}
            for i in rows:
                res[i[0]] = CallPath(i[0], i[1], i[2])
            return res


def align_to_interval(t: int) -> int:
    return g_interval * (t // g_interval)


def convert_dbs(dbs: list[str], raws: list[str]) -> list[PerfData]:
    """
    Compute approximate run time of each function from neighboring samples.
    If a new symbol appears in a sample with respect to the previous one,
    record the sample's time as the symbols's enter time.
    If a symbol disappears with respect to the previous sample, record
    the sample's time as the symbol's exit time.
    """
    res = []
    for db in dbs:
        checkDB(db)
        samples: list[Sample] = read_samples(db)
        symbols: dict[int, str] = read_symbols(db)
        callpaths: dict[int, CallPath] = read_callpaths(db)
        # recover callchain for each sample, a callchain is a list of symbol_ids
        samples_callchains = list(map(lambda sample: resolve_callchain(sample, symbols, callpaths), samples))
        # [symbol_id: [time: #times]]
        timevec: dict[int, dict[int, int]] = {}
        # [symbol_id, time]
        last_enter_time: dict[int, int] = {}
        # diff_callchain and count func run time
        prev_cc = None
        # print(samples_callchains)
        for i in range(len(samples_callchains)):
            this_sample = samples_callchains[i][0]
            this_cc = samples_callchains[i][1]
            
            if prev_cc is None:
                for n in this_cc:
                    last_enter_time[n] = this_sample.time
            else:
                nodes_new = set(this_cc) - set(prev_cc)
                # record enter time
                for n in nodes_new:
                    last_enter_time[n] = this_sample.time

                nodes_gone = set(prev_cc) - set(this_cc)
                # count run time
                for n in nodes_gone:
                    if n not in last_enter_time.keys():
                        print(f'error: call node is gone but not recorded')
                        exit(-1)

                    if symbols[n] == 'unknown' or last_enter_time[n] == 0:
                        continue
                    
                    delta = this_sample.time - last_enter_time[n]
                    left_boundary = align_to_interval(delta)
                    if timevec.get(n) == None:
                        timevec[n] = { left_boundary: 1 }
                    elif timevec[n].get(left_boundary) == None:
                        timevec[n][left_boundary] = 1
                    else:
                        timevec[n][left_boundary] += 1

            prev_cc = this_cc


        cmd = find_cmdline(db, raws)
        pd = PerfData('', cmd, '', '', g_interval)
        pd.mode = 3
        pd.buckets = len(timevec.keys())
        pd.data = timevec
        pd.symbol_dict = symbols
        # for k,v in timevec.items():
            # print(f'{symbols[k]}: {v}')
        res.append(pd)
    
    return res


def main(dir1: str, dir2: str):
    # input: perf_trec_${package}_${arch}/
    # look for: perf_trec_${package}_${arch}/perf_data/sqlite
    # and     : perf_trec_${package}_${arch}/perf_data/raw

    dataDir1 = dir1 + "/perf_data"
    dataDir2 = dir2 + "/perf_data"

    sqliteDir1 = dataDir1 + "/sqlite"
    sqliteDir2 = dataDir2 + "/sqlite"

    rawTextDir1 = dataDir1 + "/raw"
    rawTextDir2 = dataDir2 + "/raw"

    checkDir(sqliteDir1)
    checkDir(sqliteDir2)
    checkDir(rawTextDir1)
    checkDir(rawTextDir2)

    isPerfDB = lambda x: 'perf.data' in x and x.endswith('.db')
    isRaw    = lambda x: 'perf.data' in x and x.endswith('.raw')
    concatPath = lambda x: lambda y: os.path.join(x, y)

    perfDBs1 = list(map(concatPath(sqliteDir1), filter(isPerfDB, os.listdir(sqliteDir1))))
    perfDBs2 = list(map(concatPath(sqliteDir2), filter(isPerfDB, os.listdir(sqliteDir2))))

    raws1 = list(map(concatPath(rawTextDir1), filter(isRaw, os.listdir(rawTextDir1))))
    raws2 = list(map(concatPath(rawTextDir2), filter(isRaw, os.listdir(rawTextDir2))))

    if perfDBs1 == [] or perfDBs2 == [] or raws1 == [] or raws2 == []:
        print('data files are incomplete')
        exit(-1)

    perfDatas1 = convert_dbs(perfDBs1, raws1)
    perfDatas2 = convert_dbs(perfDBs2, raws2)

    matches: list[tuple[PerfData, PerfData]] = find_matches(perfDatas1, perfDatas2)

    for kv in matches:
        analyze(kv[0], kv[1])


###
### start of program
###

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='perf-data',
        description='Convert perf.data and do performance analysis.')

    parser.add_argument('dataDir1', type=str, help='directory of perf data from the 1st architecture')
    parser.add_argument('dataDir2', type=str, help='directory of perf data from the 2nd architecture')

    args = parser.parse_args()
    main(args.dataDir1, args.dataDir2)


# TODO use -F 9999 (sample ~10 times per 1ms)