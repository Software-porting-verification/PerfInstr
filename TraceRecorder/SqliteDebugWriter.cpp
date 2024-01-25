#include <cassert>
#include <string.h>

#include "SqliteDebugWriter.h"

static int query_callback(void* ret, int argc, char** argv, char** azColName) {
  assert(argc == 1);
  *(int*)ret = atoi(argv[0]);
  return 0;
}

int SqliteDebugWriter::insertName(const char* table,
                                  const char* name,
                                  std::map<std::string, uint32_t>& m) {
  char buf[4096];
  snprintf(buf, 2047, "INSERT INTO %s VALUES (NULL, \"%s\");", table, name);
  char* errmsg;
  int status = sqlite3_exec(db, buf, nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK) {
    printf("query error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);
  return queryMaxID(table);
}

int SqliteDebugWriter::insertDebugInfo(int nameA,
                                       int nameB,
                                       int line,
                                       int col) {
  char buf[4096];
  snprintf(buf, 2047, "INSERT INTO DEBUGINFO VALUES (NULL, %d, %d, %d, %d);",
           nameA, nameB, line, col);
  char* errmsg;
  int status = sqlite3_exec(db, buf, nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK) {
    printf("query error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);
  return queryMaxID("DEBUGINFO");
}

int SqliteDebugWriter::queryMaxID(const char* table) {
  char* errmsg;
  char buf[4096];
  int ID = -1;
  snprintf(buf, 4095, "select seq from sqlite_sequence where name='%s';",
           table);
  int status = sqlite3_exec(db, buf, query_callback, &ID, &errmsg);
  if (status != SQLITE_OK) {
    printf("query error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);
  if (ID == -1) {
    printf("query error: cannot query last inserted ID for table %s\n", table);
    exit(1);
  }
  return ID;
}

int SqliteDebugWriter::queryFileID(const char* name) {
  return queryID("DEBUGFILENAME", name);
}

int SqliteDebugWriter::queryVarID(const char* name) {
  return queryID("DEBUGVARNAME", name);
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

int SqliteDebugWriter::queryDebugInfoID(int nameA,
                                        int nameB,
                                        int line,
                                        int col) {
  char* errmsg;
  char buf[4096];
  int ID = -1;
  snprintf(
      buf, 4095,
      "SELECT ID from DEBUGINFO where NAMEIDA=\"%d\" AND NAMEIDB=\"%d\" AND "
      "LINE=\"%d\" AND COL=\"%d\";",
      nameA, nameB, line, col);
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

uint64_t SqliteDebugWriter::ReformID(int ID) {
  assert(DBID >= 1);
  assert(ID >= 1);
  return (((uint64_t)DBID & ((1ULL << 16) - 1)) << 48) |
          ((uint64_t)ID & ((1ULL << 48) - 1));
}

SqliteDebugWriter::SqliteDebugWriter() : db(nullptr), DBID(-1) {
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

  status = sqlite3_exec(db,
                        "CREATE TABLE MANAGER (ID INTEGER PRIMARY KEY "
                        "AUTOINCREMENT, PID INTEGER);",
                        nullptr, nullptr, &errmsg);
  if (status != SQLITE_OK &&
      !(status == SQLITE_ERROR &&
        strcmp(errmsg, "table MANAGER already exists") == 0)) {
    printf("create table error(%d): %s\n", status, errmsg);
    exit(status);
  };
  sqlite3_free(errmsg);

  bool isCreated = false;
  char buffer[256];
  snprintf(buffer, sizeof(buffer), "SELECT ID from MANAGER where PID=%d;", pid);
  status = sqlite3_exec(db, buffer, query_callback, &DBID, &errmsg);
  if (status != SQLITE_OK) {
    printf("query manager table error(%d): %s\n", status, errmsg);
    exit(status);
  };
  while (DBID == -1) {
    snprintf(buffer, sizeof(buffer),
             "SELECT ID from MANAGER where PID IS NULL;");
    status = sqlite3_exec(db, buffer, query_callback, &DBID, &errmsg);
    if (status != SQLITE_OK) {
      printf("query manager table error(%d): %s\n", status, errmsg);
      exit(status);
    };
    sqlite3_free(errmsg);
    if (DBID == -1) {
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
           pid, DBID);
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
           DBID);
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

  if (isCreated) {
    status = sqlite3_exec(db,
                          "CREATE TABLE DEBUGINFO ("
                          "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
                          "NAMEIDA INTEGER NOT NULL,"
                          "NAMEIDB INTEGER NOT NULL,"
                          "LINE SMALLINT NOT NULL,"
                          "COL SMALLINT NOT NULL);"
                          "CREATE TABLE DEBUGVARNAME ("
                          "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
                          "NAME CHAR(256));"
                          "CREATE TABLE DEBUGFILENAME ("
                          "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
                          "NAME CHAR(2048));",
                          nullptr, nullptr, &errmsg);
    if (status) {
      printf("create subtables failed %d:%s\n", status, sqlite3_errmsg(db));
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
  char buffer[256];
  snprintf(buffer, sizeof(buffer), "UPDATE MANAGER SET PID=NULL where ID=%d;",
           DBID);
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

int SqliteDebugWriter::getVarID(const char* name) {
  if (!KnownVarNames.count(name)) {
    int ID = queryVarID(name);
    if (ID == -1) {
      insertVarName(name);
    }
    KnownVarNames[name] = ID;
  }
  return KnownVarNames.at(name);
}

int SqliteDebugWriter::getDebugInfoID(int nameA, int nameB, int line, int col) {
  int ID = queryDebugInfoID(nameA, nameB, line, col);
  if (ID == -1)
    ID = insertDebugInfo(nameA, nameB, line, col);
  return ID;
}

int SqliteDebugWriter::insertFileName(const char* name) {
  insertName("DEBUGFILENAME", name, KnownFileNames);
  return queryMaxID("DEBUGFILENAME");
}

int SqliteDebugWriter::insertVarName(const char* name) {
  insertName("DEBUGVARNAME", name, KnownVarNames);
  return queryMaxID("DEBUGVARNAME");
}