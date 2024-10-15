#include <sqlite3.h>
#include <sys/file.h>
#include <unistd.h>

#include <bit>
#include <filesystem>
#include <map>

class SqliteDebugWriter {
  sqlite3* db;
  int dbID;
  std::filesystem::path DBDirPath;
  std::map<std::string, uint32_t> KnownFileNames, KnownFuncNames;
  int insert(const char* table, const char* name);
  int insertFileName(const char* name);
  int insertFuncName(const char* name);
  int queryFileID(const char* name);
  int queryFuncID(const char* name);
  int queryID(const char* table, const char* name);

 public:
  SqliteDebugWriter();
  ~SqliteDebugWriter();
  int getFileID(const char* name);
  int getFuncID(const char* name);
  uint64_t craftFID(int fileID, int funcID);
  int getBBLID(uint64_t fid, int linestart, int lineend);
  void commitSQL();
  void beginSQL();
};