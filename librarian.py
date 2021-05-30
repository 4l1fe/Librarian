import sqlite3
import logging
import sys
import csv
import io

from dataclasses import dataclass, fields as get_fields, astuple, asdict, field, Field
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter as ADHFormatter, ArgumentTypeError
from pathlib import Path
from datetime import datetime
from typing import Tuple, Generator, Union
from zlib import crc32


ISO8601 = str


class Constants:
    EXCLUDED = 'venv'
    RAW_FORMAT = 'raw'
    CSV_FORMAT = 'csv'
    SNOWBALL_SO = './fts5stemmer.so'
    STEM_LANGUAGE = 'russian'
    MAX_TOKENS = 10
    DB_FILE = 'librarian.db'
    TABLE_NAME = 'documents'
    FILE_EXTENSIONS = frozenset(('.md', ))
    RESULTS_LIMIT = 5
    AUTO_COLUMM = -1  # auto column selection
    STR_EMPTY_VALUE = "''"
    ESC_GREEN_BACK_START = "'\033[0;102m '"
    ESC_END = "' \033[0m'"
c = Constants


class FieldMetadata:
    UNINDEXED = 'unindexed'
fm = FieldMetadata


@dataclass
class _DataClass:

    @classmethod
    def fields(cls) -> Tuple[Field]:
        return get_fields(cls)

    @classmethod
    def fields_names(cls) -> Tuple[str]:
        fields = tuple(f.name for f in cls.fields())
        return fields


@dataclass(order=True)
class SnippetProperties(_DataClass):
    """fields order isn't an option, it's a requirement"""
    column_index: int = c.AUTO_COLUMM
    before_phrase: str = c.ESC_GREEN_BACK_START
    after_phrase: str = c.ESC_END
    start_or_end: str = c.STR_EMPTY_VALUE
    max_tokens: int = c.MAX_TOKENS


@dataclass(order=True)
class _BaseDocument(_DataClass):
    """repr - output option """
    path: str = field(repr=True)
    extension: str = field(repr=False)
    size: str = field(repr=False, metadata={fm.UNINDEXED: True})
    created: str = field(repr=False)
    modified: str = field(repr=False)
    hash: str = field(repr=False, metadata={fm.UNINDEXED: True})


@dataclass(order=True)
class InDocument(_BaseDocument):
    content: str = field(repr=False)


@dataclass(order=True)
class OutDocument(_BaseDocument):
    rank: str = field(repr=False)
    snippet: str = field(repr=True, metadata={'properties': SnippetProperties()})
    rowid: str = field(repr=False)

    @staticmethod
    def _repr_fields() -> Generator[Field, None, None]:
        return (f for f in OutDocument.fields() if f.repr)

    @staticmethod
    def repr_fields_names() -> Tuple[str]:
        fields = tuple(f.name for f in OutDocument._repr_fields())
        return fields
    
    def to_tuple(self, fields: Tuple[str] = None) -> Tuple[str]:
        if not fields:
            fields = self.repr_fields_names()
        
        d = asdict(self)
        return tuple(map(lambda name: d[name], fields))


class Librarian:

    def __init__(self, db=c.DB_FILE, table=c.TABLE_NAME, sql_trace=False, snippet_props: SnippetProperties = None):
        self.conn = sqlite3.connect(db)
        self.conn.load_extension(c.SNOWBALL_SO)
        self.table = table
        if sql_trace:
            self.conn.set_trace_callback(print)
        self.custom_out_snippet = None if not snippet_props else Librarian._stringify_out_snippet(table, snippet_props)

    @staticmethod
    def _stringify_out_snippet(table, snippet_properties) -> str:
        return "snippet({table}, {idx}, {before}, {after}, {start_end}, {tokens})"\
               .format(table=table, idx=snippet_properties.column_index, before=snippet_properties.before_phrase,
                       after=snippet_properties.after_phrase, start_end=snippet_properties.start_or_end,
                       tokens=snippet_properties.max_tokens)

    @staticmethod
    def _stringify_in_fields():
        pathes = (f.name + ' UNINDEXED' if f.metadata.get(fm.UNINDEXED) else f.name for f in InDocument.fields())
        return ', '.join(pathes)

    def _stringify_out_fields(self):
        fields = OutDocument.fields()
        names = []
        for f in fields:
            name = f.name
            if name == 'snippet':
                name = self.custom_out_snippet or Librarian._stringify_out_snippet(self.table, f.metadata['properties'])
            names.append(name)

        return ', '.join(names)

    def _hash(self, content: str) -> str:
        _hash = crc32(content.encode())
        return str(_hash)

    @staticmethod
    def _to_iso(timestamp: Union[int, float]) -> ISO8601:
        return datetime.utcfromtimestamp(timestamp).isoformat()

    def _delete(self, document: OutDocument):
        self.conn.execute(f"""DELETE FROM {self.table}
                              WHERE rowid={document.rowid};""")
        self.conn.commit()
        logging.info('Deleted: %s', document.path)

    def create_fts5_table(self):
        fields = self._stringify_in_fields()
        self.conn.execute(f"""CREATE VIRTUAL TABLE IF NOT EXISTS {self.table} 
                              USING FTS5({fields}, tokenize='snowball {c.STEM_LANGUAGE}');""")

    def index(self, target, extensions=c.FILE_EXTENSIONS):  # TODO ignore hard "samefile()", soft links "is_symlink". Check duplications
        target = Path(target)

        def _documents_iter():
            documents = (target, ) if target.is_file() else target.rglob('*')
            for p in documents:
                if c.EXCLUDED in p.as_posix():
                    logging.debug('Excluded: %s', p.as_posix())
                    continue

                if p.suffix not in extensions:
                    logging.debug('Excluded: %s', p.as_posix())
                    continue

                logging.debug('Indexed: %s', p.as_posix())
                content = p.read_text()
                stats = p.stat()
                d = InDocument(path=p.as_posix(),
                               content=content,
                               extension=p.suffix,
                               size=stats.st_size,
                               created=self._to_iso(stats.st_ctime),
                               modified=self._to_iso(stats.st_mtime),
                               hash=self._hash(content))
                yield astuple(d)

        with self.conn:
            placeholder = '(' + ','.join('?' for _ in range(len(InDocument.fields()))) + ')'
            for document in _documents_iter():
                logging.debug('Write: %s', document)
                self.conn.execute(f"INSERT INTO {self.table} VALUES {placeholder};", document)
                self.conn.commit()

    def match(self, query, fields: Tuple[str] = None, limit=c.RESULTS_LIMIT) -> Tuple[Tuple[str]]:
        cur = self.conn.cursor()
        stfd_fields = self._stringify_out_fields()
        cur.execute(f"""SELECT {stfd_fields}
                        FROM {self.table} 
                        WHERE {self.table}  
                        MATCH '{query}'
                        LIMIT {limit};""")
        return tuple(OutDocument(*row).to_tuple(fields=fields) for row in cur)

    def update(self, clean=False):
        cur = self.conn.cursor()
        upd_cur = self.conn.cursor()
        stfd_fields = self._stringify_out_fields()
        cur.execute(f"SELECT {stfd_fields} FROM {self.table};")

        for row in cur:
            d = OutDocument(*row)
            p = Path(d.path)
            logging.debug("Check: %s", d.path)
            if not p.exists():
                if clean:
                    self._delete(d)
                else:
                    logging.warning("Document doesn't exist: %s", d.path)
                continue

            stats = p.stat()
            if self._to_iso(stats.st_mtime) == d.modified:  # Avoid disk reading
                continue
            content = p.read_text()
            check_hash = self._hash(content)
            if check_hash != d.hash:
                modified = datetime.utcfromtimestamp(stats.st_mtime).isoformat()
                upd_cur.execute(f"""UPDATE {self.table} 
                                    SET content='{content}', size={stats.st_size}, modified='{modified}', hash={check_hash} 
                                    WHERE rowid={d.rowid}""")
                self.conn.commit()
                logging.info('Updated: %s', d.path)


class ArgPHelper:

    @staticmethod
    def default_fields() -> Tuple[str]:
        return OutDocument.repr_fields_names()

    @staticmethod
    def fields_choices() -> Tuple[str]:
        return OutDocument.fields_names()

    @staticmethod
    def fields_type(string) -> tuple:
        args = string.strip().split(',')
        fields = ArgPHelper.fields_choices()
        valid_fields = set(args) & set(fields)
        if not valid_fields:
            raise ArgumentTypeError('Has to be contain at least one valid name.')

        ordered = filter(lambda f: f in valid_fields, args)
        return tuple(ordered)

    @staticmethod
    def snippet_props_type(string) -> SnippetProperties:
        idx, *values, maxt = string.strip().split(',')
        wrapper = lambda value: "'" + value + "'"
        values = tuple((value:= wrapper(v) if v else c.STR_EMPTY_VALUE)
                  for v in values)

        return SnippetProperties(int(idx), *values, int(maxt))


def form_args():
    parser = ArgumentParser(formatter_class=ADHFormatter)
    parser.add_argument('--db', default=c.DB_FILE, help='DB file path.')
    parser.add_argument('--table', default=c.TABLE_NAME, help='Table name to store files content.')
    parser.add_argument('--debug', action='store_true', help='Flag of print additional events.')
    parser.add_argument('--sql-trace', action='store_true', help='Flag of print sqlite statements.')
    subparsers = parser.add_subparsers(title='available commands', description='Use -h with each of them to get help.',
                                       dest='command', required=True)

    index_parser = subparsers.add_parser('index', formatter_class=ADHFormatter,
                                         help='Command to build a db and index. Have to be run once.')
    index_parser.add_argument('target', help='Directory or a file to build an index on.')
    index_parser.add_argument('--file-extensions', type=frozenset, default=c.FILE_EXTENSIONS,
                              metavar='string', help='List of file extensions separated by space which to scan only.')
    index_parser.add_argument('--language', default=c.STEM_LANGUAGE,
                              help="list of available languages https://snowballstem.org/algorithms/")

    match_parser = subparsers.add_parser('match', formatter_class=ADHFormatter,
                                          help='Command to run query on indexed files.')
    match_parser.add_argument('query', help='Sqlite query term executed by "MATCH" statement. '
                                            'Syntax can be found on https://sqlite.org/fts5.html#full_text_query_syntax.')
    match_parser.add_argument('--limit', default=c.RESULTS_LIMIT, help='Max count of results.')
    match_parser.add_argument('--fields', dest='fields', metavar='field,...', type=ArgPHelper.fields_type,
                              default=ArgPHelper.default_fields(),
                              help=f'List of document fields to retrieve separated by comma, order is preserved. '
                                   f'Choices: {ArgPHelper.fields_choices()}.')
    match_parser.add_argument('--format', default=c.CSV_FORMAT,
                              choices=(c.RAW_FORMAT, c.CSV_FORMAT), help='Choose a results output format.')
    match_parser.add_argument('--snippet', default=None, type=ArgPHelper.snippet_props_type,  metavar="1,'','','','',10",
                              help='Snippet properties settings https://sqlite.org/fts5.html#the_snippet_function')

    update_parser = subparsers.add_parser('update', formatter_class=ADHFormatter,
                                          help='Command to check if content is changed and update in the database.')
    update_parser.add_argument('--clean', action='store_true', help="Delete missing file records")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()

    return args


if __name__ == '__main__':
    args = form_args()

    lbn = Librarian(db=args.db, table=args.table, sql_trace=args.sql_trace, snippet_props=args.snippet)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, stream=sys.stdout,
                        format='%(message)s')

    if args.command == 'index':
        lbn.create_fts5_table()
        lbn.index(args.target, extensions=args.file_extensions)
    elif args.command == 'match':
        logging.debug(args.query)
        documents = lbn.match(args.query, fields=args.fields, limit=args.limit)
        if args.format == c.CSV_FORMAT and documents:
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(args.fields)
            writer.writerows(documents)
            documents = out.getvalue()
        logging.info(documents)
    elif args.command == 'update':
        lbn.update(clean=args.clean)
