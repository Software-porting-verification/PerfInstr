---
author: Mao Yifu
documentclass: ctexart
number-sections: true
toc: true
papersize: a4
lang: zh
geometry:
  - top=20mm
  - left=20mm
  - right=20mm
---

# 简介

本工具通过对C/C++程序插桩，在运行时动态记录函数的运行时间及次数，保存为性能数据。
之后通过对性能数据的分析生成函数级性能报告。

本工具包含以下组件：

- 插桩插件(`Pass/`)
- 数据收集运行时(`perfRT/`)
- 插桩编译脚本(`perf-clang`, `perf-clang++`)
- 性能分析脚本(`perf_*.py`)

支持的架构：

- x64
- riscv64
- aarch64

工具使用大致流程：

1. 使用`perf-clang`/`perf-clang++`在不同平台插桩编译被测程序，
2. 运行被测程序，得到性能数据，
3. 使用`perf_func.py`集中分析不同平台的性能数据，生成报告。


# 构建插桩插件和数据收集运行时

环境要求：GNU/Linux, Python 3, LLVM/clang 17及以上。
另需以下python库：

- `numpy`
- `jinja2`
- `matplotlib`
- `scipy`
- `scikit-learn`

本工具要求构建插桩插件时使用的LLVM头文件版本需和使用该插件时的LLVM版本保持一致。

```bash
# 可选，手动指定LLVM路径
export LLVM_DIR=path/to/llvm/

mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=`pwd`/install
ninja install -j4
```

安装完成后，插桩插件，数据收集运行时，在`CMAKE_INSTALL_PREFIX/lib[64]`目录下，
插桩编译脚本在`CMAKE_INSTALL_PREFIX/bin`目录下。


# 使用说明

本节以压缩工具`brotli`为例，讲解如何使用本工具测试对比其在x64和riscv64平台上的性能。
以下步骤需要分别在x64和riscv64平台上操作，以凸显测试效果。
若无可用riscv64平台系统，也可将运行程序的步骤执行两次，并确保存储两次性能数据的目录分开。

为了简化后续测试流程，程序源码，调试信息目录和性能数据目录按如下结构放置：

```
brotli_test
├── debuginfo
├── perf_data
└── src 
      └── brotli
```

另外需要注意，两个平台上`brotli_test`的路径前缀需一致，以简化后续分析。

后文的`TREC_DATABASE_DIR`和`TREC_PERF_DIR`将分别设置为`debuginfo`和`perf_data`的绝对路径。


## 获取`brotli`源码

在上文展示的`src`目录下克隆`brotli`源码：

```bash
$ git clone --depth=1 https://github.com/google/brotli.git brotli
$ cd brotli
```

## 程序插桩编译

程序插桩编译仅需将默认C和C++编译器替换为`perf-clang`和`perf-clang++`，并设置相关环境变量：

```bash
$ export CC=path/to/perf-clang
$ export CXX=path/to/perf-clang++

# 设置编译器插桩时存放调试信息的目录，
# 该目录存储源码符号等信息，用于后续报告呈现
$ export TREC_DATABASE_DIR=$DEBUG_DIR
```

构建程序：

```bash
$ mkdir -p build && cd build
$ cmake ..
$ make -j
```


## 运行程序，收集性能数据

`brotli`构建完成后，可以手动运行`brotli`，或者运行其测试用例来得到性能数据。这里我们运行其测试用例。

在插桩的程序运行之前，需要通过环境变量放置性能数据的目录以及数据收集模式：

```bash
# 配置放置性能数据的目录 
$ export TREC_PERF_DIR=path/to/perf_data
# 配置数据收集模式
$ export TREC_PERF_MODE=time
```

运行`brotli`测试用例：

```bash
$ make test
```

执行完成后，可在`TREC_PERF_DIR`下看到生成的性能数据：

```bash
$ ls $TREC_PERF_DIR
```

```
trec_perf_brotli_13032.bin  trec_perf_brotli_13113.bin
trec_perf_brotli_13192.bin  trec_perf_brotli_13290.bin
...
```

性能数据命名格式为`trec_perf_程序名_进程号.bin`。


## 分析数据

将两个架构的`brotli_test`目录放在同一台机器，分别命名为`brotli_test_x64`和`brotli_test_riscv64`。
调用分析脚本分析：

```bash
./perf_func.py brotli_test_x64 brotli_test_riscv64 \
    --prefix parent/dir/to/brotli --name brotli
```

其中`--prefix`选项指定存放`brotli`源码的绝对路径前缀，`--name`指定报告名称。

脚本执行完成后会在当前目录生成`brotli.html`，内含函数级性能报告。
默认情况下，若第二个架构的函数耗时是第一个架构的1.8x及以上，则该函数包含到报告中。
报告中的函数按照性能损失从大到小排序。


# 额外配置

插桩后的程序在运行时为每一个运行到的函数开辟一个固定大小的频次数组存储该函数的调用次数。
该频次数组的下标表示该函数一次运行的耗时范围。
频次数组默认长度是4096，耗时范围默认是250ns。
所以当函数耗时在250ns以下时，其对应频次数组的第一个元素加1；
当函数耗时在250ns到500ns时，其对应频次数组的第二个元素加1，以此类推。


## 设置性能数组长度

通过环境变量`TREC_PERF_BUCKET_COUNT`可以设置性能数组长度，以适应不同的计数精确度和内存占用。
有效的值在1024至4096之间。


## 设置记录的时间粒度

通过环境变量`TREC_PERF_INTERVAL`可以设置以纳秒为单位的耗时范围，以适应不同的计数精确度。
有效值为正整数。


# 故障排除


## 调试信息数据库路径未配置

调试信息数据库路径未配置时，编译器报错类似：

```
ERROR: ENV variable `TREC_DATABASE_DIR` has not been set!
```

解决方法：在构建程序前设置`TREC_DATABASE_DIR`环境变量。


## 性能数据存放目录未配置

性能数据存放目录未配置，程序运行时报错：

```
[perfRT] env TREC_PERF_DIR not set!
```

解决方法：在程序运行前设置`TREC_PERF_DIR`环境变量。


## 数据收集模式未配置

若数据收集模式未配置，则程序运行后无性能数据。

解决方法：在运行程序前设置`TREC_PERF_MODE`为`time`。


## 报告中显示源码获取失败：src not found

若报告中的源码部分显示为`src not found`，
且`perf_func.py`运行过程中打印出`Dir of file not found`，
则源码路径前缀未正确设置。

解决方法：运行`perf_func.py`时正确设置设置`--prefix`。
例如，当`brotli`的源码路径为`/home/user/brotli`是，设置`--prefix /home/user`。