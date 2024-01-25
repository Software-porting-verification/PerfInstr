#include <sqlite3.h>
#include <sys/file.h>
#include <unistd.h>
#include <bit>
#include <filesystem>
#include <map>

class SqliteDebugWriter {
  sqlite3* db;
  int DBID;
  std::filesystem::path DBDirPath;
  std::map<std::string, uint32_t> KnownFileNames, KnownVarNames;
  int insertName(const char* table,
                 const char* name,
                 std::map<std::string, uint32_t>& m);
  int insertDebugInfo(int nameA, int nameB, int line, int col);
  int insertFileName(const char* name);
  int insertVarName(const char* name);
  int queryMaxID(const char* table);
  int queryFileID(const char* name);
  int queryVarID(const char* name);
  int queryID(const char* table, const char* name);
  int queryDebugInfoID(int nameA, int nameB, int line, int col);

 public:
  SqliteDebugWriter();
  ~SqliteDebugWriter();
  int getFileID(const char* name);
  int getVarID(const char* name);
  int getDebugInfoID(int nameA, int nameB, int line, int col);
  uint64_t ReformID(int ID);
  void commitSQL();

  void beginSQL();
};