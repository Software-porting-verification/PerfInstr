#include <cassert>
#include <cstdint>
#include <cstdio>
#include <string.h>

#include "SqliteDebugWriter.h"

const char * SQL_TABLE_FILENAMES = "FILENAMES";
const char * SQL_TABLE_FUNCNAMES = "FUNCNAMES";
const char * SQL_TABLE_BBLS      = "BBLS";

const char * SQL_CREATE_MANAGER = 
  "CREATE TABLE MANAGER ("
    "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
    "PID INTEGER);";

const char * SQL_CREATE_TABLES = 
  "CREATE TABLE FILENAMES ("
    "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
    "NAME CHAR(2048));"
  "CREATE TABLE FUNCNAMES ("
    "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
    "NAME CHAR(256));"
  "CREATE TABLE BBLS ("
    "ID  INTEGER PRIMARY KEY AUTOINCREMENT,"
    "FID INTEGER,"
    "LINESTART INTEGER,"
    "LINEEND   INTEGER);";

static int query_callback(void* ret, int argc, char** argv, char** azColName) {
  assert(argc == 1);
  *(int*)ret = atoi(argv[0]);
  return 0;
}

SqliteDebugWriter::SqliteDebugWriter() : db(nullptr), dbID(-1) {
  char* DatabaseDir = getenv("TREC_DATABASE_DIR");
  if (DatabaseDir == nullptr) {
    printf("ERROR: ENV variable `TREC_DATABASE_DIR` has not been set!\n");
    exit(-1);
  }
  DBDirPath = std::filesystem::path(DatabaseDir);
  int pid = getpid();
  std::filesystem::path managerDBPath =
      DBDirPath / std::filesystem::path("manager.db");
  int status;
  char* errmsg;

  // open sqlite database
  status = sqlite3_open(managerDBPath.c_str(), &db);
  if (status) {
    printf("Open manager databased %s failed(%d): %s\n", managerDBPath.c_str(),
           status, sqlite3_errmsg(db));
    exit(status);
  }

  // acquire flock
  int database_fd = open(managerDBPath.c_str(), O_RDONLY);
  if ((status = flock(database_fd, LOCK_EX)) != 0) {
    printf("ERROR: acquire flock for manager database %s failed(%d)\n",
           managerDBPath.c_str(), status);
    exit(status);
  }

  status = sqlite3_exec(db, SQL_CREATE_MANAGER, nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK &&
      !(status == SQLITE_ERROR &&
        strcmp(errmsg, "table MANAGER already exists") == 0)) {
    printf("create table error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);

  /// try to get a db id from pid
  bool isCreated = false;
  char buffer[256];
  snprintf(buffer, sizeof(buffer), "SELECT ID from MANAGER where PID=%d;", pid);
  status = sqlite3_exec(db, buffer, query_callback, &dbID, &errmsg);
  if (status != SQLITE_OK) {
    printf("query manager table error(%d): %s\n", status, errmsg);
    exit(status);
  };
  while (dbID == -1) {
    // If there's a null pid, it's key can be the db id.
    snprintf(buffer, sizeof(buffer),
             "SELECT ID from MANAGER where PID IS NULL;");
    status = sqlite3_exec(db, buffer, query_callback, &dbID, &errmsg);
    if (status != SQLITE_OK) {
      printf("query manager table error(%d): %s\n", status, errmsg);
      exit(status);
    };
    sqlite3_free(errmsg);

    // try to make a row with null pid
    if (dbID == -1) {
      // no empty entry
      isCreated = true;
      snprintf(buffer, sizeof(buffer),
               "INSERT INTO MANAGER VALUES (NULL, NULL);");
      while ((status = sqlite3_exec(db, buffer, nullptr, nullptr, &errmsg)) ==
             SQLITE_BUSY)
        sqlite3_free(errmsg);
      sqlite3_free(errmsg);
      if (status != SQLITE_OK) {
        printf("insert manager table error(%d): %s\n", status, errmsg);
        exit(status);
      };
      sqlite3_free(errmsg);
    }
  }

  snprintf(buffer, sizeof(buffer), "UPDATE MANAGER SET PID=%d where ID=%d;",
           pid, dbID);
  status = sqlite3_exec(db, buffer, nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK) {
    printf("update manager table error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);

  // release flock
  if ((status = flock(database_fd, LOCK_UN)) != 0) {
    printf("ERROR: release flock failed\n");
    exit(status);
  }
  close(database_fd);

  // close manager database
  sqlite3_close(db);

  snprintf(buffer, sizeof(buffer), "%s/debuginfo%d.db", DBDirPath.c_str(),
           dbID);
  sqlite3_open(buffer, &db);
  if (status) {
    printf("open %s file failed(%d): %s\n", buffer, status, sqlite3_errmsg(db));
    exit(status);
  }

  // speedup querying
  status =
      sqlite3_exec(db, "PRAGMA synchronous=OFF;", nullptr, nullptr, nullptr);
  if (status != SQLITE_OK) {
    printf("trun off synchronous mode failed: %s\n", sqlite3_errmsg(db));
    exit(status);
  }

  // printf("creating subtables\n");
  if (isCreated) {
    status = sqlite3_exec(db, SQL_CREATE_TABLES, nullptr, nullptr, &errmsg);
    if (status) {
      printf("create debuginfo tables failed %d:%s\n", status, sqlite3_errmsg(db));
      exit(status);
    }
    sqlite3_free(errmsg);
  }
}

SqliteDebugWriter::~SqliteDebugWriter() {
  sqlite3_close(db);

  std::filesystem::path managerDBPath =
      DBDirPath / std::filesystem::path("manager.db");
  int status;
  char* errmsg;
  int database_fd = open(managerDBPath.c_str(), O_RDONLY);
  if ((status = flock(database_fd, LOCK_EX)) != 0) {
    printf("ERROR: acquire flock failed\n");
    exit(status);
  }

  status = sqlite3_open(managerDBPath.c_str(), &db);
  if (status) {
    printf("Open manager databased %s failed(%d): %s\n", managerDBPath.c_str(),
           status, sqlite3_errmsg(db));
    exit(status);
  }

  // Release the dbID.
  char buffer[256];
  snprintf(buffer, sizeof(buffer), "UPDATE MANAGER SET PID=NULL where ID=%d;",
           dbID);
  status = sqlite3_exec(db, buffer, nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK) {
    printf("update manager table error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);

  sqlite3_close(db);
  if ((status = flock(database_fd, LOCK_UN)) != 0) {
    printf("ERROR: release flock failed\n");
    exit(status);
  }
  close(database_fd);
}

int SqliteDebugWriter::getFileID(const char* name) {
  if (!KnownFileNames.count(name)) {
    int ID = queryFileID(name);
    if (ID == -1) {
      ID = insertFileName(name);
    }
    KnownFileNames[name] = ID;
  }
  return KnownFileNames.at(name);
}

int SqliteDebugWriter::getFuncID(const char* name) {
  if (!KnownFuncNames.count(name)) {
    int ID = queryFuncID(name);
    if (ID == -1) {
      ID = insertFuncName(name);
    }
    KnownFuncNames[name] = ID;
  }
  return KnownFuncNames.at(name);
}

int SqliteDebugWriter::queryFileID(const char* name) {
  return queryID(SQL_TABLE_FILENAMES, name);
}

int SqliteDebugWriter::queryFuncID(const char* name) {
  return queryID(SQL_TABLE_FUNCNAMES, name);
}

uint64_t SqliteDebugWriter::getBBLID(uint64_t fid, int linestart, int lineend) {
  char buf[4096];
  snprintf(buf, 4095, "INSERT INTO %s VALUES (NULL, %ld, %d, %d);", SQL_TABLE_BBLS, fid, linestart, lineend);
  char* errmsg;
  int status = sqlite3_exec(db, buf, nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK) {
    printf("query error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);

  int id = sqlite3_last_insert_rowid(db);
  auto bblid = ((uint64_t) (dbID & 0xffff) << 48) | ((uint64_t) (id & 0xffffffffffff));
  printf("SqliteDebugWriter::getBBLID: %lu, fid: %lu, bbl_id: %d\n", bblid, fid, id);

  return bblid;
}

int SqliteDebugWriter::queryID(const char* table, const char* name) {
  char* errmsg;
  char buf[4096];
  int ID = -1;
  snprintf(buf, 4095, "SELECT ID from %s where NAME=\"%s\";", table, name);
  int status = sqlite3_exec(db, buf, query_callback, &ID, &errmsg);
  if (status != SQLITE_OK) {
    printf("query error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);
  return ID;
}

void SqliteDebugWriter::commitSQL() {
  char* errmsg;
  int status;
  while ((status = sqlite3_exec(db, "COMMIT;", nullptr, nullptr, &errmsg)) ==
         SQLITE_BUSY)
    sqlite3_free(errmsg);
  sqlite3_free(errmsg);
  if (status != SQLITE_OK) {
    printf("commit sqlite error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);
}

void SqliteDebugWriter::beginSQL() {
  char* errmsg;
  int status = sqlite3_exec(db, "BEGIN;", nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK) {
    printf("begin sqlite error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);
}

uint64_t SqliteDebugWriter::craftFID(int fileID, int funcID) {
  // printf("dbID: %d, fileID: %d, funcID: %d\n", dbID, fileID, funcID);
  assert(dbID >= 1 && fileID >= 1 && funcID >= 1);
  assert((dbID < (1 << 16)) && (fileID < (1 << 24)) && (funcID < (1 << 24)));

  return ((uint64_t) (dbID & 0xffff) << 48) | ((uint64_t) (fileID & 0xffffff) << 24) | funcID;
}

int SqliteDebugWriter::insertFileName(const char* name) {
  return insert(SQL_TABLE_FILENAMES, name);
}

int SqliteDebugWriter::insertFuncName(const char* name) {
  return insert(SQL_TABLE_FUNCNAMES, name);
}

int SqliteDebugWriter::insert(const char* table, const char* name) {
  char buf[4096];
  snprintf(buf, 2047, "INSERT INTO %s VALUES (NULL, \"%s\");", table, name);
  char* errmsg;
  int status = sqlite3_exec(db, buf, nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK) {
    printf("query error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);

  return queryID(table, name);
}