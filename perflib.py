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
from pathlib import Path
import matplotlib.pyplot as plt


g_obs_prefix = '/home/abuild/rpmbuild/BUILD/'


class PerfData:
    # dict[fid, list[counts]]
    rawData: dict[int, list[int]]
    # dict[fid, dict[interval, counts]]
    data: dict[int, dict[int, int]]
    # 0: time, 1: cycle, 2: insn, 3: perf
    mode: int
    numOfFuncs: int
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


    def get_file_name(self, func: str, fid):
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
    def __init__(self, func: str, pd1: PerfData, pd2: PerfData, dist1: list[float], dist2: list[float], fid1, fid2):
        self.func = func
        self.pd1  = pd1
        self.pd2  = pd2
        self.dist1 = dist1
        self.dist2 = dist2
        self.fid1 = fid1
        self.fid2 = fid2


def decodeFid(fid):
    dbID   = (fid >> 48) & 0xffff
    fileID = (fid >> 24) & 0xffffff
    funcID = fid & 0xffffff

    return dbID, funcID, fileID


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


def analyze(pd1: PerfData, pd2: PerfData) -> list[PerfResult]:
    # print('cmd:', pd1.cmd)
    pd1_data = {}
    pd2_data = {}
    paired_data1 = {}
    paired_data2 = {}
    pd1_fid: dict[str, fid] = {}
    pd2_fid: dict[str, fid] = {}
    # print(pd1.data)
    results: list[PerfResult] = []
    
    for fid in pd1.data.keys():
        if len(pd1.data[fid])<=1:
            continue
        func = pd1.get_symbol_name(fid)
        pd1_data[func] = pd1.data[fid]
        pd1_fid[func]  = fid
        
    for fid in pd2.data.keys():
        if len(pd2.data[fid])<=1:
            continue
        func = pd2.get_symbol_name(fid)
        #pd2_data[func] = [fid, pd2.data[fid]]
        pd2_data[func] = pd2.data[fid]
        pd2_fid[func]  = fid
    
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
                results.append(PerfResult(func, pd1, pd2, income_t, income_c, pd1_fid[func], pd2_fid[func]))

    return results


def choose_the_most_serious(results: list[PerfResult]) -> PerfResult:
    # TODO
    return results[0]


def analyze_all(perfDatas1: list[PerfData], perfDatas2: list[PerfData]):
    matches: list[tuple[PerfData, PerfData]] = find_matches(perfDatas1, perfDatas2)
    if matches == []:
        print('No match found')
        exit(0)
    res: list[PerfResult] = []
    for kv in matches:
        res += analyze(kv[0], kv[1])

    res_by_name: dict[str, list[PerfResult]] = {}
    for r in res:
        if r.func in res_by_name.keys():
            res_by_name[r.func].append(r)
        else:
            res_by_name[r.func] = [r]
    # for results with the same func name, choose the most "serious" distritution
    true_res: list[PerfResult] = list(map(choose_the_most_serious, res_by_name.values()))

    return true_res


# TODO arr name should be arch
def generate_plot(res: PerfResult, path: str, arr1_name='', arr2_name=''):
    file = f'{path}/{res.func}'
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
    return p
    # plt.show()


def fetch_source_code(res: PerfResult) -> list[str]:
    # NAME from db is like: /home/abuild/rpmbuild/BUILD/aide-0.18.5/lex.yy.c
    # remove prefix and concat with srcDir
    bare_name = res.pd1.get_file_name(res.func, res.fid1).removeprefix(g_obs_prefix)
    src_file = res.pd1.srcDir + bare_name
    checkFile(src_file)
    # get line, for perf-instr, line num is in `func`
    nameline = res.func.split(':')
    name = nameline[0]
    # -1 to include the function name decl
    line = int(nameline[1].strip()) - 1

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
    return srcs, bare_name


class ReportItem:
    def __init__(self, func: str, code: str, file: str, pic: str):
        self.func = func
        self.code = code
        self.file = file
        self.pic = pic


def generate_report(results: list[PerfResult], path = '.'):
    # gen HTML
    # gen plot
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
        loader=PackageLoader("perf-instr"),
        autoescape=select_autoescape()
    )
    template = env.get_template('report.html')
    with open(f'{filename}.html', 'w') as f:
        f.write(template.render(perf_package = filename, reports = reports))
    print('rendered')
    
