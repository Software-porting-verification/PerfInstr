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
from enum import Enum
import yaml
import argparse
import sqlite3
import struct
from contextlib import closing
from pathlib import Path
import matplotlib.pyplot as plt
import hashlib


g_obs_prefix = '/home/abuild/rpmbuild/BUILD/'
g_bad_threshold = 0.8


def set_g_obs_prefix(p: str):
    global g_obs_prefix
    g_obs_prefix = p


def get_g_obs_prefix():
    global g_obs_prefix
    return g_obs_prefix


def set_g_bad_threshold(t):
    global g_bad_threshold
    g_bad_threshold = t


def get_g_bad_threshold():
    global g_bad_threshold
    return g_bad_threshold


# aligned with perfRT
class PerfArch(Enum):
    X64     = 0
    RISCV64 = 1
    ARM64   = 2


# aligned with perfRT
class PerfDataType(Enum):
    TIME  = 0
    CYCLE = 1
    INSN  = 2
    PERF  = 3
    TIME_BBL = 4


class PerfData:
    # dict[fid, list[counts]]
    rawData: dict[int, list[int]]
    # dict[fid, dict[interval, counts]]
    data: dict[int, dict[int, int]]
    # 0: time, 1: cycle, 2: insn, 3: perf, 4: time_bbl
    mode: int
    buckets: int
    dbDir: str = None
    srcDir: str = None
    symbol_dict: dict[int, str] = None


    def __init__(self, dataPath: str, cmd: str, exe: str, pwd: str, interval: int):
        # path of this data file
        self.dataPath = dataPath
        # cmdline and arguments
        self.cmd = cmd
        # path of the testcase executable
        self.exe = exe
        # path of the testcase's working directory
        self.pwd = pwd
        # time interval on the frequency vector
        self.interval = interval
        self.rawData = {}
        self.data = {}
        self.package = None
        self.arch = None
        self.type = None

    
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
        elif self.mode == 4:
            # BBL mode
            dbID, bbid = decodeBBLid(sid)
            dbName = f"{self.dbDir}/debuginfo{dbID}.db"
            if dbID < 0:
                print(f"Less than 0: {dbID}")
            checkDB(dbName)
            with closing(sqlite3.connect(dbName)) as connection:
                with closing(connection.cursor()) as cursor:
                    rows = cursor.execute("select FID from BBLS where ID=?", (bbid,)).fetchall()
                    _, funcID, _ = decodeFid(rows[0][0])
                    rows = cursor.execute("select NAME from FUNCNAMES where ID=?", (funcID,)).fetchall()
                    return rows[0][0]
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


    def get_bbl_lines(self, bblid):
        if not self.mode == 4:
            print(f'get_bbl_lines() is only available in BBL mode.')
            exit(-1)

        dbID, bbid = decodeBBLid(bblid)
        dbName = f"{self.dbDir}/debuginfo{dbID}.db"
        if dbID < 0:
            print(f"Less than 0: {dbID}")
        checkDB(dbName)
        with closing(sqlite3.connect(dbName)) as connection:
            with closing(connection.cursor()) as cursor:
                rows = cursor.execute("select LINESTART,LINEEND from BBLS where ID=?", (bbid,)).fetchall()
                return rows[0][0], rows[0][1]


    def get_bbl_fid(self, bblid):
        if not self.mode == 4:
            print(f'get_bbl_fid() is only available in BBL mode.')
            exit(-1)

        dbID, bbid = decodeBBLid(bblid)
        dbName = f"{self.dbDir}/debuginfo{dbID}.db"
        if dbID < 0:
            print(f"Less than 0: {dbID}")
        checkDB(dbName)
        with closing(sqlite3.connect(dbName)) as connection:
            with closing(connection.cursor()) as cursor:
                rows = cursor.execute("select FID from BBLS where ID=?", (bbid,)).fetchall()
                return rows[0][0]


    def get_file_name(self, fid):
        dbID, funcID, fileID = decodeFid(fid)
        dbName = f"{self.dbDir}/debuginfo{dbID}.db"
        if dbID < 0:
            print(f"Less than 0: {dbID}")
        checkDB(dbName)
        with closing(sqlite3.connect(dbName)) as connection:
            with closing(connection.cursor()) as cursor:
                rows = cursor.execute("select NAME from FILENAMES where ID=?", (fileID,)).fetchall()
                return rows[0][0]


class PerfResult:
    def __init__(self, func: str, pd1: PerfData, pd2: PerfData, dist1: list[float], dist2: list[float], fid1, fid2, ratio=0.0):
        self.func = func
        self.pd1  = pd1
        self.pd2  = pd2
        self.dist1 = dist1
        self.dist2 = dist2
        self.fid1 = fid1
        self.fid2 = fid2
        self.ratio = ratio


def read_perf_data(data_path: str) -> PerfData:
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
        # print(f"cmd: {cmd}, exe: {exe}, pwd: {pwd}")
        # print(f"exeParams: {exeParams}")

        # <: little endian
        mode   = struct.unpack('<b', bs[i   : i+1])[0]
        arch   = struct.unpack('<b', bs[i+1 : i+2])[0]
        length = struct.unpack('<i', bs[i+2 : i+6])[0]
        interval = struct.unpack('<i', bs[i+6 : i+10])[0]
        # print(f"mode: {mode}, bucket length: {length}")

        perfData = PerfData(data_path, cmd, exe, pwd, interval)
        perfData.mode = mode
        perfData.buckets = length
        perfData.type = PerfDataType(mode)
        perfData.arch = PerfArch(arch)

        # read each function's counts
        len_fid_buckets = (length + 1) * 8
        num_func  = (len(bs) - (1 + 4)) // len_fid_buckets
        # print(f"Number of functions: {num_func}")

        # data : fid -> bucket
        data = {}
        start = i + 10
        for i in range(num_func):
            fid = struct.unpack('<Q', bs[start:start + 8])[0]
            start += 8
            vec = []
            for bucket_i in range(length):
                vec.append(struct.unpack('<q', bs[start:start + 8])[0])
                start += 8

            perfData.addRawData(fid, vec)
        
        return perfData


def dump_perf_data(p: str, src_dir:str, db_path: str):
    d = read_perf_data(p)
    d.srcDir = src_dir
    d.dbDir = db_path

    print(f'file: {p}')
    print(f'cmd:  {d.cmd}')
    print(f'exe:  {d.exe}')
    print(f'pwd:  {d.pwd}')
    if d.mode == 0:
        print('mode: time')
    elif d.mode == 1:
        print('mode: cycle')
    elif d.mode == 2:
        print('mode: instruction')
    elif d.mode == 3:
        print('mode: perf command')
    elif d.mode == 4:
        print('mode: time bbl')
    else:
        print('invalid mode: ' + d.mode)
        exit(-1)
    print(f'interval: {d.interval}ns')
    print(f'#buckets: {d.buckets}')
    print('Data:')
    print(f'\tentries: {len(d.data.keys())}')
    if d.type == PerfDataType.TIME:
        print(f'\t{'id':<30} {'count':<10} symbol')
        for fid, times in d.data.items():
            print(f'\t{fid:<30} {sum(times.values()):<10} {d.get_symbol_name(fid)}')
    elif d.type == PerfDataType.TIME_BBL:
        print(f'\t{'bblid':<30} {'fid':<30} {'count':<10} symbol')
        for bblid, times in d.data.items():
            fid = d.get_bbl_fid(bblid)
            print(f'\t{bblid:<30} {fid:<30} {sum(times.values()):<10} {d.get_symbol_name(bblid)}')


def decodeFid(fid):
    dbID   = (fid >> 48) & 0xffff
    fileID = (fid >> 24) & 0xffffff
    funcID = fid & 0xffffff

    return dbID, funcID, fileID


def decodeBBLid(bblid):
    dbID   = (bblid >> 48) & 0xffff
    bbID = bblid & 0xffffffffffff

    return dbID, bbID


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
        print(f"Dir of file not found: {path}")
        exit(-4)


def checkFileNoExit(path: str):
    if os.path.exists(path):
        if not os.path.isfile(path):
            print(f"Not a file: {path}")
            return False
    else:
        print(f"Dir of file not found: {path}")
        return False

    return True


def checkDB(path):
    if os.path.exists(path):
        if not os.path.isfile(path):
            print(f"Not a database file: {path}")
            exit(-1)
    else:
        print(f"Database file not found: {path}")
        exit(-1)


def find_matches(perfDatas1: list[PerfData], perfDatas2: list[PerfData]) -> list[tuple[PerfData, PerfData]]:
    # print('Looking for matching perf data...')
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

    # print('Done')
    return matches


def find_matches_star(perf_data_list_list: list[list[PerfData]]):
    print('Looking for multiple matching perf data...')
    # make sets of cmd in each list of PerfData and do intersection
    list_of_sets_of_cmd: list[set[str]] = \
        list(map(lambda ds: set(map(lambda d: d.cmd, ds)), perf_data_list_list))

    common_cmds = list_of_sets_of_cmd[0]
    for s in list_of_sets_of_cmd[1:]:
        common_cmds = common_cmds & s
    
    # print(f'find_matches_start: common_cmds: {common_cmds}')

    # a list of lists of matching PerfData
    matches: list[list[PerfData]] = []
    for cmd in common_cmds:
        matching_perf_data = []
        for pds in perf_data_list_list:
            for pd in pds:
                if pd.cmd == cmd:
                    matching_perf_data.append(pd)
                    break
        assert len(matching_perf_data) == len(perf_data_list_list)
        matches.append(matching_perf_data)

    return matches


import numpy as np
from scipy.stats import ttest_ind, mannwhitneyu, ks_2samp, chisquare
from sklearn import preprocessing
from scipy import stats


def normalize(arr1):
    arr1_np=np.array(arr1)
    return (arr1_np-arr1_np.min())/(arr1_np.max()-arr1_np.min())


# prepare data in PerfData for analysis
def prepare_data(data):
    times1 = []
    for k,v in data.items():
        times1+=[k for i in range(0,v)]
    return normalize(times1)


def analyze_data(d1, d2):
    d1 = prepare_data(d1)
    d2 = prepare_data(d2)

    # statistics, pvalues = ttest_ind(income_t,income_c)
    # statistics, pvalues = mannwhitneyu(income_t,income_c)
    # statistics, pvalues = chisquare(income_t,income_c)
    statistics, pvalues = ks_2samp(d1, d2)
    if pvalues < statistics:
        # bad
        return False, d1, d2
    else:
        # good
        return True, d1, d2


def analyze(pd1: PerfData, pd2: PerfData) -> list[PerfResult]:
    # print('cmd:', pd1.cmd)
    pd1_data = {}
    pd2_data = {}
    paired_data1 = {}
    paired_data2 = {}
    pd1_fid: dict[str, int] = {}
    pd2_fid: dict[str, int] = {}
    pd1_rawData: dict[str, int] = {}
    pd2_rawData: dict[str, int] = {}
    # print(pd1.data)
    results: list[PerfResult] = []
    good_ones = []
    
    for fid in pd1.data.keys():
        if len(pd1.data[fid])<=1:
            continue
        func = pd1.get_symbol_name(fid)
        pd1_data[func] = pd1.data[fid]
        pd1_rawData[func] = pd1.rawData[fid]
        pd1_fid[func]  = fid
        
    for fid in pd2.data.keys():
        if len(pd2.data[fid])<=1:
            continue
        func = pd2.get_symbol_name(fid)
        #pd2_data[func] = [fid, pd2.data[fid]]
        pd2_data[func] = pd2.data[fid]
        pd2_rawData[func] = pd2.rawData[fid]
        pd2_fid[func]  = fid
    
    for func in pd1_data.keys():
        if func in pd2_data:
            times1=[]
            # k: left time interval, i.e., [k, k')
            # v: number of times
            # duplicate each k, v times
            for k,v in pd1_data[func].items():
                times1+=[k for i in range(0,v)]
            times1=normalize(times1)
            paired_data1[func] = times1
            
            times2=[]
            for k,v in pd2_data[func].items():
                times2+=[k for i in range(0,v)]
            times2=normalize(times2)
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
                results.append(PerfResult(func, pd1, pd2, pd1_rawData[func], pd2_rawData[func], pd1_fid[func], pd2_fid[func]))
            else:
                good_ones.append(PerfResult(func, pd1, pd2, pd1_rawData[func], pd2_rawData[func], pd1_fid[func], pd2_fid[func]))

    return results, good_ones


def compare_time(buckets, interval1, raw_data1: list[int], interval2, raw_data2: list[int]):
    # raw_data1 should come from the faster machine
    interv1 = np.array([i for i in range(0, buckets * interval1, interval1)])
    interv2 = np.array([i for i in range(0, buckets * interval2, interval2)])
    d1 = np.array(raw_data1)
    d2 = np.array(raw_data2)

    t1 = np.sum(interv1 * d1)
    t2 = np.sum(interv2 * d2)

    r = (t2 / t1) - 1
    if r >= get_g_bad_threshold():
        # bad result
        return False, r
    return True, r


def analyze_time(pd1: PerfData, pd2: PerfData) -> list[PerfResult]:
    paired_data1 = {}
    paired_data2 = {}
    pd1_fid: dict[str, int] = {}
    pd2_fid: dict[str, int] = {}
    pd1_rawData: dict[str, int] = {}
    pd2_rawData: dict[str, int] = {}
    bad_ones:  list[PerfResult] = []
    good_ones: list[PerfResult] = []
    
    for fid in pd1.data.keys():
        if len(pd1.data[fid])<=1:
            continue
        func = pd1.get_symbol_name(fid)
        pd1_rawData[func] = pd1.rawData[fid]
        pd1_fid[func]  = fid
        
    for fid in pd2.data.keys():
        if len(pd2.data[fid])<=1:
            continue
        func = pd2.get_symbol_name(fid)
        pd2_rawData[func] = pd2.rawData[fid]
        pd2_fid[func]  = fid
    
    # find data with the same function name
    for func1, d1 in pd1_rawData.items():
        if func1 in pd2_rawData.keys():
            paired_data1[func1] = d1
            paired_data2[func1] = pd2_rawData[func1]

    for func in paired_data1.keys():
        if func in paired_data2:
            dist1=paired_data1[func]
            dist2=paired_data2[func]

            # assuming two data have the same length
            is_good, ratio = compare_time(pd1.buckets, pd1.interval, dist1, pd2.interval, dist2)
            if is_good:
                good_ones.append(PerfResult(func, pd1, pd2, pd1_rawData[func], pd2_rawData[func], pd1_fid[func], pd2_fid[func], ratio))
            else:
                bad_ones.append(PerfResult(func, pd1, pd2, pd1_rawData[func], pd2_rawData[func], pd1_fid[func], pd2_fid[func], ratio))

    return bad_ones, good_ones


def choose_the_most_serious(results: list[PerfResult]) -> PerfResult:
    # TODO use the navbar approach to avoid this
    return results[0]


def analyze_all(perfDatas1: list[PerfData], perfDatas2: list[PerfData]):
    print('Preparing to analyze...')

    matches: list[tuple[PerfData, PerfData]] = find_matches(perfDatas1, perfDatas2)
    if matches == []:
        print('No match found')
        exit(0)
    res: list[PerfResult] = []
    goods_res: list[PerfResult] = []

    print('Analyzing...')

    for kv in matches:
        bad, good = analyze_time(kv[0], kv[1])
        res += bad
        goods_res += good

    res_by_name: dict[str, list[PerfResult]] = {}
    good_res_by_name: dict[str, list[PerfResult]] = {}
    for r in res:
        if r.func in res_by_name.keys():
            res_by_name[r.func].append(r)
        else:
            res_by_name[r.func] = [r]

    for r in goods_res:
        if r.func in good_res_by_name.keys():
            good_res_by_name[r.func].append(r)
        else:
            good_res_by_name[r.func] = [r]
    # for results with the same func name, choose the most "serious" distritution
    # true_res: list[PerfResult] = list(map(choose_the_most_serious, res_by_name.values()))
    # true_good_res: list[PerfResult] = list(map(choose_the_most_serious, good_res_by_name.values()))

    print('Done.')

    res.sort(key=lambda pr: pr.ratio)
    res.reverse()
    # num = int(len(res) * 0.3)
    # print(f'{len(res)} results in total\n')

    return res, goods_res


# TODO arr name should be arch
def generate_plot(res: PerfResult, path: str, arr1_name='', arr2_name=''):
    # to avoid file name too long error and colon (cannot appear in file name on Windows)
    image_name = hashlib.sha256(str.encode(res.func)).hexdigest()
    file = f'{path}/{image_name}'
    arr1 = res.dist1
    arr2 = res.dist2

    # 创建画布，并设置大小和背景颜色
    fig, ax = plt.subplots(figsize=(8, 5.5), facecolor='white')

    # 绘制两个直方图：alpha控制透明度
    num_bins = 100
    if len(arr1)<100:
        num_bins=len(arr1)
    n1, bins1, patches1 = ax.hist(arr1, bins=num_bins, density=True, alpha=0.5, color='blue')
    n2, bins2, patches2 = ax.hist(arr2, bins=num_bins, density=True, alpha=0.5, color='green')

    # 设置坐标轴范围和标签
    ax.set_xlim([0, 1])
    ax.tick_params(axis='both', labelsize=25)
    ax.set_xlabel('Scaled Time', size=25)
    ax.set_ylabel('Frequency', size=25)

    # 添加标题和图例
    # plt.title('Normal Distribution Histogram Comparison')
    if arr1_name=='':
        arr1_name='arch1'
    if arr2_name == '':
        arr2_name = 'arch2'
    ax.legend([arr1_name, arr2_name], prop = {'size':25})

    # 显示图形
    plt.tight_layout()
    if not os.path.exists(path):
        os.makedirs(path)
    p = os.path.join(path, '%s.png' % file)
    plt.savefig(p)
    plt.close(fig)
    return p
    # plt.show()


def fetch_source_code(res: PerfResult) -> list[str]:
    # NAME from db is like: /home/abuild/rpmbuild/BUILD/aide-0.18.5/lex.yy.c
    # remove prefix and concat with srcDir
    bare_name = res.pd1.get_file_name(res.fid1).removeprefix(get_g_obs_prefix())
    src_file = res.pd1.srcDir + bare_name
    # get line, for perf-instr, line num is in `func`
    # use rsplit() instead of split() because of names like "OptionStorageTemplate<gmx::BooleanOption>: 401"
    nameline = res.func.rsplit(':', 1)
    name = nameline[0]
    # -1 to include the function name decl
    line = int(nameline[1].strip()) - 1

    if checkFileNoExit(src_file):
        # open file and read several lines
        with open(src_file, 'r') as f:
            lines = f.readlines()
            linenum = len(lines)
            lcount = 19
            # select only 5 lines or so
            if line < linenum:
                if line + lcount >= linenum:
                    srcs = lines[line:linenum]
                else:
                    srcs = lines[line:line+lcount]
            else:
                print(f'Error: func {name} line {line} exceeding file lines ({linenum})')
        srcs.append('[...]')
    else:
        srcs = ['src not found']

    return srcs, bare_name

def fetch_source_code_by_id(d: PerfData, sym_name: str, id: int, src_prefix: str) -> list[str]:
    # NAME from db is like: /home/abuild/rpmbuild/BUILD/aide-0.18.5/lex.yy.c
    # remove prefix and concat with srcDir
    bare_name = d.get_file_name(id).removeprefix(src_prefix)
    src_file = d.srcDir + bare_name
    # get line, for perf-instr, line num is in `func`
    # use rsplit() instead of split() because of names like "OptionStorageTemplate<gmx::BooleanOption>: 401"
    nameline = sym_name.rsplit(':', 1)
    name = nameline[0]
    # -1 to include the function name decl
    line = int(nameline[1].strip()) - 1

    if checkFileNoExit(src_file):
        # open file and read several lines
        with open(src_file, 'r') as f:
            lines = f.readlines()
            linenum = len(lines)
            lcount = 19
            # select only 5 lines or so
            if line < linenum:
                if line + lcount >= linenum:
                    srcs = lines[line:linenum]
                else:
                    srcs = lines[line:line+lcount]
            else:
                print(f'Error: func {name} line {line} exceeding file lines ({linenum})')
        srcs.append('[...]')
    else:
        srcs = ['src not found']

    return srcs


def fetch_source_code_range(pd: PerfData, func: str, fid, start, end):
    # NAME from db is like: /home/abuild/rpmbuild/BUILD/aide-0.18.5/lex.yy.c
    # remove prefix and concat with srcDir
    bare_name = pd.get_file_name(fid).removeprefix(get_g_obs_prefix())
    src_file = pd.srcDir + bare_name
    # get line, for perf-instr, line num is in `func`
    # use rsplit() instead of split() because of names like "OptionStorageTemplate<gmx::BooleanOption>: 401"
    # nameline = func.rsplit(':', 1)
    # name = nameline[0]
    # -1 to include the function name decl
    # line = int(nameline[1].strip()) - 1

    if checkFileNoExit(src_file):
        # open file and read several lines
        with open(src_file, 'r') as f:
            lines = f.readlines()
            srcs = lines[start:end+1]
    else:
        srcs = ['src not found']

    return srcs, bare_name


class ReportItem:
    def __init__(self, func: str, code: str, file: str, pic: str):
        self.func = func
        self.code = code
        self.file = file
        self.pic = pic


class BBLReportItem:
    def __init__(self, code: list[str], file: str, pic: str):
        # code corresponding to the BBL
        self.code = code
        # source file path
        self.file = file
        # base64 encoding of the plot
        self.pic = pic


class BBLFuncReport:
    def __init__(self, func: str):
        self.func = func
        self.bbl_items = []

    def add_bbl_items(self, bblitem: BBLReportItem):
        self.bbl_items.append(bblitem)


class BBLReport:
    def __init__(self, pd: PerfData):
        self.perf_data  = pd
        self.func_items = []

    def add_func_items(self, funcitem: BBLFuncReport):
        self.func_items.append(funcitem)



def generate_report(results: list[PerfResult], path = '.'):
    # gen HTML
    # gen plot
    print(f'Generating report for {len(results)} results...')
    reports: ReportItem = []
    for res in results:
        srcs, src_file = fetch_source_code(res)
        # print(res.func)
        ss = ''
        for s in srcs:
            ss += s
        pic = generate_plot(res, path)
        reports.append(ReportItem(res.func, ss, src_file, pic))

    if reports == []:
        return

    filename = Path(reports[0].file).parts[0]

    from jinja2 import Environment, PackageLoader, select_autoescape
    env = Environment(
        loader=PackageLoader("perflib"),
        autoescape=select_autoescape()
    )
    template = env.get_template('report.html')
    with open(f'{filename}.html', 'w') as f:
        print('Rendering report...')
        f.write(template.render(perf_package = filename, reports = reports))
    print('Rendered.')
    