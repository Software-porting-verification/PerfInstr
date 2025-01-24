# rvbench算分说明

注意：算分要求rvbench生成的数据目录结构如下：

```
machine1
    pkg1
        test_1
            src
            debuginfo
            perf_data
        test_2
            ...
    pkg2
    ...
machine2
    pkg1
        test_1
            src
            debuginfo
            perf_data
        test_2
            ...
    pkg2
    ...
```

各级目录除了对应的平台，包以及多次运行的`test_N`，不能包含别的目录。
以下所有脚本在装有数据目录的*顶层目录*执行。
在上文中，顶层目录为`machine*`的父目录。

Python版本必须>=3.12。

## 算分

算分使用`rvbench_score.fish`脚本。
使用该脚本时，需*按顺序*传入`RVBENCH_TEST`和`RVBENCH_SUMMARIZE`两个参数，
其中`RVBENCH_TEST`为本项目`rvbench_test_star.py`脚本*绝对路径*，
`RVBENCH_SUMMARIZE`为本项目`rvbench_summarize.py`脚本*绝对路径*，
例如：

```bash
./rvbench_score.fish $(pwd)/rvbench_test_star.py $(pwd)/rvbench_summarize.py
```

在顶层目录执行`rvbench_score.fish`后，会在各个`pkg`目录生成：

- N.csv: 每个测试用例的分数，包含各个函数的分数以及所有函数分数加总；
- total.csv: 该包中所有测试用例的分数加总。

当前目录会生成`sumN.csv`，包含利用各个算分算法的所有包在各个平台的总分。


## 如何新增打分算法

`rvbench_test_star.py`中的`g_scorers`变量存储了各个打分算法的名称及打分函数。
打分函数为每一个测试用例的函数算分。例如：

```py
def compute_time(pd: PerfData, fid: int, func_name: str, raw_data: list[int]):
    # pd: 该函数所在性能数据文件对象
    # fid: 函数fid
    # func_name: 函数名
    # raw_data： 性能数据数组
    w = np.array([i for i in range(pd.interval, pd.interval * (pd.buckets + 1), pd.interval)])
    d = np.array(raw_data)
    s = (w * d).sum().item()

    return s
```

新增打分函数只需在`g_scorers`中新增一项包含算分名称和打分函数的列表。
新增打分函数签名需和上面的函数签名保持一致。
之后，算分脚本生成的文件会自动包含新增算法的结果。
