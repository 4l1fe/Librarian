![](icon.png)

# Librarian

I'll found what had been in your mind but hasn't been in there.

## Usage

### General options

```bash
$ ./librarian.py -h
usage: librarian.py [-h] [--db DB] [--table TABLE] [--debug] {index,match} ...

optional arguments:
  -h, --help     show this help message and exit
  --db DB        DB file path. (default: fts.db)
  --table TABLE  Table name to store files content. (default: documents)
  --debug        Print additional events and sqlite statements. (default: False)

available commands:
  Use -h with each of them to get help.

  {index,match}
    index        Command to build a db and index. Have to be run once.
    match        Command to run query on indexed files.
```

### Indexing your text files

```bash
$ ./librarian.py index -h
usage: librarian.py index [-h] [--file-extensions string] target

positional arguments:
  target                Directory to build an index on.

optional arguments:
  -h, --help            show this help message and exit
  --file-extensions string
                        List of file extensions separated by space which to scan only. (default:
                        frozenset({'.md'}))
```

### Searching

```bash
$ ./librarian.py match -h
usage: librarian.py match [-h] [--limit LIMIT] [--format {raw,md,csv}] query

positional arguments:
  query                 Sqlite query term executed by "MATCH" statement. Syntax can be found on
                        https://sqlite.org/fts5.html#full_text_query_syntax.

optional arguments:
  -h, --help            show this help message and exit
  --limit LIMIT         Max count of results. (default: 5)
  --format {raw,md,csv}
                        Chose a results output format. (default: raw)
```

