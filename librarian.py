import sqlite3
import logging
import sys
import csv
import io

from dataclasses import dataclass, fields as get_fields, astuple, asdict, field, Field
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter as ADHFormatter, ArgumentTypeError
from pathlib import Path
from datetime import datetime
from typing import Tuple, Generator


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
c = Constants


class FieldMetadata:
    UNINDEXED = 'unindexed'
    SUBSTITUTE = 'substitute'
fm = FieldMetadata


@dataclass(order=True)
class _BaseDocument:
    """repr - output option """
    path: str = field(repr=True)
    extension: str = field(repr=False)
    size: str = field(repr=False, metadata={fm.UNINDEXED: True})
    created: str = field(repr=False)
    modified: str = field(repr=False)

    @classmethod
    def fields(cls) -> Tuple[Field]:
        return get_fields(cls)


@dataclass(order=True)
class InDocument(_BaseDocument):
    content: str = field(repr=False)


@dataclass(order=True)
class OutDocument(_BaseDocument):
    rank: str = field(repr=False)
    snippet: str = field(repr=True, metadata={fm.SUBSTITUTE: "snippet({table}, -1, '', '', '', {max_tokens})"})
    rowid: str = field(repr=False)

    @staticmethod
    def fields_names() -> Tuple[str]:
        fields = tuple(f.name for f in OutDocument.fields())
        return fields

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


class Config:

    @staticmethod
    def default_fields() -> Tuple[str]:
        return OutDocument.repr_fields_names()

    @staticmethod
    def fields_choices() -> Tuple[str]:
        return OutDocument.fields_names()


class Librarian:

    def __init__(self, db=c.DB_FILE, table=c.TABLE_NAME, sql_trace=False):
        self.conn = sqlite3.connect(db)
        self.table = table
        if sql_trace:
            self.conn.set_trace_callback(print)

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
                name = f.metadata[fm.SUBSTITUTE]
                name = name.format(table=self.table, max_tokens=c.MAX_TOKENS)
            names.append(name)

        return ', '.join(names)

    def create_fts5_table(self):
        self.conn.load_extension(c.SNOWBALL_SO)
        fields = self._stringify_in_fields()
        self.conn.execute(f"""CREATE VIRTUAL TABLE IF NOT EXISTS {self.table} 
                              USING FTS5({fields}, tokenize='snowball {c.STEM_LANGUAGE}');""")

    def index(self, target, extensions=c.FILE_EXTENSIONS):

        def _documents_iter():
            for p in Path(target).rglob('*'):
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
                               created=datetime.utcfromtimestamp(stats.st_ctime).isoformat(),
                               modified=datetime.utcfromtimestamp(stats.st_mtime).isoformat())
                yield astuple(d)

        with self.conn:
            placeholder = '(' + ','.join('?' for _ in range(len(InDocument.fields()))) + ')'
            for document in _documents_iter():
                logging.debug(f'Write: {document}')
                self.conn.execute(f"INSERT INTO {self.table} VALUES {placeholder};", document)

    def match(self, query, fields: Tuple[str] = None, limit=c.RESULTS_LIMIT) -> Tuple[Tuple[str]]:
        cur = self.conn.cursor()
        stringified = self._stringify_out_fields()
        cur.execute(f"""SELECT {stringified}
                        FROM {self.table} 
                        WHERE {self.table}  
                        MATCH '{query}'
                        LIMIT {limit};""")
        return tuple(OutDocument(*row).to_tuple(fields=fields) for row in cur)


def fields_type(arg) -> tuple:
    args = arg.strip().split(',')
    fields = Config.fields_choices()
    valid_fields = set(args) & set(fields)
    if not valid_fields:
        raise ArgumentTypeError('Has to be contain at least one valid name.')

    ordered = filter(lambda f: f in valid_fields, args)
    return tuple(ordered)


def form_args():
    parser = ArgumentParser(formatter_class=ADHFormatter)
    subparsers = parser.add_subparsers(title='available commands', description='Use -h with each of them to get help.',
                                       dest='command', required=True)
    index_parser = subparsers.add_parser('index', formatter_class=ADHFormatter,
                                         help='Command to build a db and index. Have to be run once.')
    match_parser = subparsers.add_parser('match', formatter_class=ADHFormatter,
                                          help='Command to run query on indexed files.')

    parser.add_argument('--db', default=c.DB_FILE, help='DB file path.')
    parser.add_argument('--table', default=c.TABLE_NAME, help='Table name to store files content.')
    parser.add_argument('--debug', action='store_true', help='Flag of print additional events.')
    parser.add_argument('--sql-trace', action='store_true', help='Flag of print sqlite statements.')

    index_parser.add_argument('target', help='Directory to build an index on.')
    index_parser.add_argument('--file-extensions', type=frozenset, default=c.FILE_EXTENSIONS,
                              metavar='string', help='List of file extensions separated by space which to scan only.')
    index_parser.add_argument('--language', default=c.STEM_LANGUAGE,
                              help="list of available languages https://snowballstem.org/algorithms/")

    match_parser.add_argument('query', help='Sqlite query term executed by "MATCH" statement. '
                                            'Syntax can be found on https://sqlite.org/fts5.html#full_text_query_syntax.')
    match_parser.add_argument('--limit', default=c.RESULTS_LIMIT, help='Max count of results.')
    match_parser.add_argument('--fields', dest='fields', metavar='field,...', type=fields_type,
                              default=Config.default_fields(),
                              help=f'List of document fields to retrieve separated by comma, order is preserved. '
                                   f'Choices: {Config.fields_choices()}.')
    match_parser.add_argument('--format', default=c.RAW_FORMAT,
                              choices=(c.RAW_FORMAT, c.CSV_FORMAT), help='Choose a results output format.')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()

    return args


if __name__ == '__main__':
    args = form_args()

    lbn = Librarian(db=args.db, table=args.table, sql_trace=args.sql_trace)
    lbn.create_fts5_table()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, stream=sys.stdout,
                        format='%(message)s')

    if args.command == 'index':
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