#! /usr/bin/env python3

####################################################
#
#
# cross-architecture conformity analysis tool 
#
# Author: Mao Yifu, maoif@ios.ac.cn
#
#
####################################################



import os
import sys
import struct
import argparse
from perflib import *
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import ticker


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


def read_symbols(db: str) -> dict[int, str]:
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


# Each perf.data db corresponds to one ConformityData.
class ConformityData:
    def __init__(self, callchains: list[list[int]], cmd, symbols: dict[int, str]):
        self.callchains = callchains
        self.cmd = cmd
        self.symbols = symbols


def convert_dbs(dbs: list[str], raws: list[str]) -> list[ConformityData]:
    res = []
    for db in dbs:
        checkDB(db)
        samples: list[Sample] = read_samples(db)
        symbols: dict[int, str] = read_symbols(db)
        callpaths: dict[int, CallPath] = read_callpaths(db)
        # recover callchain for each sample, a callchain is a list of symbol_ids
        # has to be strict because of update in commonize_symbol_ids
        samples_callchains = list(map(lambda sample: resolve_callchain(sample, symbols, callpaths), samples))

        cmd = find_cmdline(db, raws)
        callchains = map(lambda kv: kv[1], samples_callchains)
        cd = ConformityData(callchains, cmd, symbols)

        res.append(cd)
    
    return res


def commonize_symbol_ids(datas1: list[ConformityData], datas2: list[ConformityData]):
    """Make symbols with the same name have the same id so we can do comparison across architectures."""
    # symbol -> new id
    symtab: dict[str, int] = {}
    new_id = 0

    def collect(data: ConformityData):
        for old_id, sym in data.symbols.items():
            if sym not in symtab.keys():
                nonlocal new_id
                symtab[sym] = new_id
                new_id += 1

    for d in datas1: collect(d)
    for d in datas2: collect(d)

    symbols: dict[int, str] = { k:v for v,k in symtab.items() }

    def update(data: ConformityData):
        data.callchains = map(lambda cc: list(map(lambda sid: symtab[data.symbols[sid]], cc)), data.callchains)
        data.symbols = symbols

    for d in datas1: update(d)
    for d in datas2: update(d)

    return symbols


def calc_freq(cdata: ConformityData) -> dict[int, int]:
    freq: dict[int, int] = {}
    for cc in cdata.callchains:
        if len(cc) >= 2:
            for i in range(1, len(cc) - 2):
                caller = cc[i]
                callee = cc[i+1]
                # optimization
                k = caller << 32 | callee
                if k in freq.keys():
                    freq[k] += 1
                else:
                    freq[k] = 1
    return freq


from scipy.stats import ttest_ind, mannwhitneyu, ks_2samp, chisquare


def analyze(cdata1: ConformityData, cdata2: ConformityData):
    # compute the caller-callee frequency of two arches, then compare
    freq1: dict[int, int] = calc_freq(cdata1)
    freq2: dict[int, int] = calc_freq(cdata2)
    # res = []
    
    # TODO what does this mean?
    # for k,v in freq1.items():
    #     flat_freq1 = [k for i in range(0, v)]
    # for k,v in freq2.items():
    #     flat_freq2 = [k for i in range(0, v)]

    # flat_freq1 = standardlization(flat_freq1)
    # flat_freq2 = standardlization(flat_freq2)
    # statistics, pvalues = ks_2samp(flat_freq1, flat_freq2)
    # if pvalues < statistics:
    #     res.append((cdata1, cdata2))

    # compare similarity of two matrices,
    # or find out the top N caller-callee that differ the most?
    # accumulate all data?
    
    diff: dict[int, int] = {}
    for cc1 in freq1.keys():
        if cc1 in freq2.keys():
            delta = abs(freq1[cc1] - freq2[cc1])
        else:
            delta = freq1[cc1]
        diff[cc1] = delta

    # normalize
    # low = min(diff.values())
    # d = max(diff.values()) - low
    # for k in diff.keys():
    #     diff[k] = (diff[k]- low) / d

    # sort the result by call count
    res = sorted([(k,v) for k,v in diff.items()], key=lambda kv: kv[1], reverse=True)
    return res


import matplotlib.pyplot as plt


def main(dir1: str, dir2: str):
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

    datas1 = convert_dbs(perfDBs1, raws1)
    datas2 = convert_dbs(perfDBs2, raws2)

    symbols = commonize_symbol_ids(datas1, datas2)

    # TODO check types
    matches = find_matches(datas1, datas2)

    diffs: list[list[tuple[int, int]]] = map(lambda m: analyze(m[0], m[1]), matches)
    N = 10
    final_diffs = []

    for diff in diffs:
        if len(diff) >= 10:
            final_diffs.append(diff[:N])
        else:
            final_diffs.append(diff)

    # compute common top N caller-callee pairs with the biggest count difference
    res = {}
    for diff in final_diffs:
        # cc, c: caller-callee, count
        for cc, c in diff:
            if cc in res.keys():
                res[cc] += c
            else:
                res[cc] = c

    sorted_res = sorted([(k,v) for k,v in res.items()], key=lambda kv: kv[1], reverse=True)
    sorted_res = sorted_res if len(sorted_res) <= N else sorted_res[:N]

    print(f'sizeof res: {len(sorted_res)} res: {sorted_res}')

    ccs = list(map(lambda kv: kv[0], sorted_res))
    counts = list(map(lambda kv: kv[1], sorted_res))
    caller_callee = list(map(lambda x: f'{symbols[x >> 32]}() -> {symbols[x & 0xffffff]}()', ccs))

    fig, ax = plt.subplots()
    ax.barh(np.arange(len(counts)), counts, tick_label=caller_callee)

    plt.show()
    # TODO draw plot that displays the top N caller-callee with color intensity


###
### start of program
###

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Convert perf.data and do conformity analysis.')

    parser.add_argument('dataDir1', type=str, help='directory of perf data from the 1st architecture')
    parser.add_argument('dataDir2', type=str, help='directory of perf data from the 2nd architecture')

    args = parser.parse_args()
    main(args.dataDir1, args.dataDir2)