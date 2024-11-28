#!/usr/bin/env fish

# rvbench_test_star.py脚本绝对路径
set RVBENCH_TEST /home/maoif/SSD/WORK/RISCV_XianDao/PerfInstr/rvbench_test_star.py
# rvbench_summarize.py脚本绝对路径
set RVBENCH_SUMMARIZE /home/maoif/SSD/WORK/RISCV_XianDao/PerfInstr/rvbench_summarize.py

# 计算所有测试用例的分数
for m in */
    cd $m
    for p in */
        cd $p
        echo Computing $m $p
        # 计算每个测试用例的分数，生成total.csv
        $RVBENCH_TEST -o ./ test_*
        cd ..
    end
    cd ..
end

# 汇总分数，生成sumN.csv
find . -name total.csv > files
$RVBENCH_SUMMARIZE ./files ./
rm -f files

