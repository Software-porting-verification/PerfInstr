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
import sqlite3
from contextlib import closing
from perflib import *


###
### start of program
###

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Dump perf data.')
    parser.add_argument('data_file', type=str, help='path to perf data file')
    parser.add_argument('src_dir', type=str, help='path to src dir')
    parser.add_argument('debuginfo', type=str, help='path to debuginfo dir')

    args = parser.parse_args()
    if os.path.isfile(args.data_file) and os.path.isdir(args.src_dir) and os.path.isdir(args.debuginfo):
        dump_perf_data(args.data_file, args.src_dir, args.debuginfo)