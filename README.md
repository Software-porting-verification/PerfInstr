# TraceRecorder (Out-of-Source-Tree Version)

An out-of-source-tree TraceRecorder.

Requirement:
    Clang & LLVM 15 or higher

Build:
```
    $ mkdir build
    $ cd build
    $ cmake ..
    $ make
    $ cd ..
```


Run:

    $ clang -g -fno-discard-value-names -fpass-plugin=lib/TraceRecorder.so something.c -L<path/to/libclang_rt.trec> -L<path/to/libclang_rt.trec_cxx> -L<other/required/system/libraries>
