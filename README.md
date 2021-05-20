![](icon.png)

# Librarian

*I'll found what had been in your mind but hasn't been in there.*

## Overview

Simple **cli commands** upon your text files which you want to search through in a smart way applying full text search technique with no cumbersome software.

**Importable abstractions** exposed as cli commands are designed to be reused on your need. You may plug them into your service.

**Single file utility**. Python and sqlite only.

## Requirements

1. `Python$ ./configure --enable-loadable-sqlite-extensions` - python complied sqlite binaries with [enabled extensions to load](https://docs.python.org/3/library/sqlite3.html#f1) `fts5`. No further settings required in code.
2. `fts5stemmer.so` - compiled shared library to index target files with [your preferable language](https://github.com/abiliojr/fts5-snowball). 

## Usage

### Common options

```shell
$ python librarian.py -h
usage: librarian.py [-h] [--db DB] [--table TABLE] [--debug] [--sql-trace] {index,match} ...

optional arguments:
  -h, --help     show this help message and exit
  --db DB        DB file path. (default: librarian.db)
  --table TABLE  Table name to store files content. (default: documents)
  --debug        Flag of print additional events. (default: False)
  --sql-trace    Flag of print sqlite statements. (default: False)

available commands:
  Use -h with each of them to get help.

  {index,match}
    index        Command to build a db and index. Have to be run once.
    match        Command to run query on indexed files.
```

### Indexing your text files

```bash
$ python librarian.py index -h
usage: librarian.py index [-h] [--file-extensions string] [--language LANGUAGE] target

positional arguments:
  target                Directory to build an index on.

optional arguments:
  -h, --help            show this help message and exit
  --file-extensions string
                        List of file extensions separated by space which to scan only. (default: frozenset({'.md'}))
  --language LANGUAGE
```

### Searching

```bash
$ python librarian.py match -h
usage: librarian.py match [-h] [--limit LIMIT] [--fields field,...] [--format {raw,md,csv}] query

positional arguments:
  query                 Sqlite query term executed by "MATCH" statement. Syntax can be found on
                        https://sqlite.org/fts5.html#full_text_query_syntax.

optional arguments:
  -h, --help            show this help message and exit
  --limit LIMIT         Max count of results. (default: 5)
  --fields field,...    List of document fields to retrieve separated by comma, order is preserved. Choices: ('name', 'extension',
                        'size', 'created', 'modified'). (default: ('name',))
  --format {raw,md,csv}
                        Chose a results output format. (default: raw)
```

## Example

Let's build a db.

```
$ python librarian.py --debug --sql-trace index ~/Text-files-documents
SELECT fts5(NULL)
CREATE VIRTUAL TABLE IF NOT EXISTS documents 
                              USING FTS5(name, content, extension, sizee, created, modified, tokenize='snowball russian');
Excluded: /home/user/Text-files-documents/Today
Excluded: /home/user/Text-files-documents/Yesterday
Indexed: /home/user/Text-files-documents/Project/README.md
...
```

And try it out.

```
$ python librarian.py match --fields created,name тесты
[(1620583081.3579128,
 '/home/user/Text-files-documents/Project/README.md',
 'Для запуска тестов нужно поднимать докер-сервисы\n   \n\n### Описание запуска'),
 ...
```

