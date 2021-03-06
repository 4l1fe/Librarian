![](icon.png)

# Librarian

*I'll find what had been in your mind but hasn't been in there.*

## Overview

Simple **cli commands** upon your text files which you want to search through in a smart way applying full text search technique with no cumbersome software.

**Importable abstractions** exposed as cli commands are designed to be reused on your need. You may plug them into your service.

**Single file utility**. Python and sqlite only.

## Requirements

1. `Python$ ./configure --enable-loadable-sqlite-extensions` - python complied sqlite binaries with [enabled extensions to load](https://docs.python.org/3/library/sqlite3.html#f1) `fts5`. No further settings required in code.
2. `fts5stemmer.so` - [compiled shared library](https://github.com/abiliojr/fts5-snowball) for indexing target files with [your preferable language](https://snowballstem.org/algorithms/). 

## Usage

### Common options

```shell
$ python librarian.py -h
usage: librarian.py [-h] [--db DB] [--table TABLE] [--debug] [--sql-trace] {index,match,update} ...

optional arguments:
  -h, --help            show this help message and exit
  --db DB               DB file path. (default: librarian.db)
  --table TABLE         Table name to store files content. (default: documents)
  --debug               Flag of print additional events. (default: False)
  --sql-trace           Flag of print sqlite statements. (default: False)

available commands:
  Use -h with each of them to get help.

  {index,match,update}
    index               Command to build a db and index. Have to be run once.
    match               Command to run query on indexed files.
    update              Command to check if content is changed and update in the database.
```

### Indexing your text files

```shell
$ python librarian.py index -h
usage: librarian.py index [-h] [--file-extensions string] [--language LANGUAGE] target

positional arguments:
  target                Directory or a file to build an index on.

optional arguments:
  -h, --help            show this help message and exit
  --file-extensions string
                        List of file extensions separated by space which to scan only. (default: frozenset({'.md'}))
  --language LANGUAGE   list of available languages https://snowballstem.org/algorithms/ (default: russian)

```

### Searching

```shell
$ python librarian.py match -h
usage: librarian.py match [-h] [--limit LIMIT] [--fields field,...] [--format {raw,csv}] [--snippet 1,'','','','',10] query

positional arguments:
  query                 Sqlite query term executed by "MATCH" statement. Syntax can be found on https://sqlite.org/fts5.html#full_text_query_syntax.

optional arguments:
  -h, --help            show this help message and exit
  --limit LIMIT         Max count of results. (default: 5)
  --fields field,...    List of document fields to retrieve separated by comma, order is preserved. Choices: ('path', 'extension', 'size', 'created', 'modified', 'hash', 'rank', 'snippet', 'rowid'). (default:
                        ('path', 'snippet'))
  --format {raw,csv}    Choose a results output format. (default: csv)
  --snippet 1,'','','','',10
                        Snippet properties settings https://sqlite.org/fts5.html#the_snippet_function (default: None)
```

### Updating

```shell
$  python librarian.py update -h
usage: librarian.py update [-h] [--clean]

optional arguments:
  -h, --help  show this help message and exit
  --clean     Delete missing file records (default: False)
```



## Example

Let's build a db.

```shell
$ python librarian.py --debug --sql-trace index ~/Text-files-documents
SELECT fts5(NULL)
CREATE REAL TABLE IF NOT EXISTS documents 
                              USING FTS5(path, content, extension, sizee, created, modified, tokenize='snowball russian');
Excluded: /home/user/Text-files-documents/Today
Excluded: /home/user/Text-files-documents/Yesterday
Indexed: /home/user/Text-files-documents/Project/README.md
...
```

And try it out.

```shell
$ python librarian.py match --fields created,path ??????????
[(1620583081.3579128,
 '/home/user/Text-files-documents/Project/README.md',
 '?????? ?????????????? ???????????? ?????????? ?????????????????? ??????????-??????????????\n   \n\n### ???????????????? ??????????????'),
 ...
```

