#!venv/bin/python
import sqlite3
import logging

from dataclasses import dataclass, fields as get_fields, astuple, field
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter as ADHFormatter, ArgumentTypeError
from pathlib import Path


class Constants:
    EXCLUDED = 'venv'
    RAW_FORMAT = 'raw'
    MD_FORMAT = 'md'
    CSV_FORMAT = 'csv'
    SNOWBALL_SO = './fts5stemmer.so'
    STEM_LANGUAGE = 'russian'
    MAX_TOKENS = 10
    DB_FILE = 'fts.db'
    TABLE_NAME = 'documents'
    FILE_EXTENSIONS = frozenset(('.md', ))
    RESULTS_LIMIT = 5
c = Constants


class FieldMetadata:
    OUTPUT = 'output'
    AVAILABLE = 'available'
fm = FieldMetadata


@dataclass(order=True)
class Document:
    name: str = field(metadata={fm.OUTPUT: True})
    content: str = field(metadata={fm.AVAILABLE: True})
    extension: str
    sizee: str  # TODO rename
    created: str
    modified: str

    @staticmethod
    def _fields_names(excluding=False) -> tuple:
        fields = tuple(f.name for f in get_fields(Document)
                       if not f.metadata.get(fm.AVAILABLE, False) or not excluding)
        return fields

    @staticmethod
    def fields_names():
        fields = Document._fields_names()
        return fields

    @staticmethod
    def available_fields_names():
        fields = Document._fields_names(excluding=True)
        return fields


class Config:

    @staticmethod
    def default_fields() -> tuple:
        return tuple(f.name for f in get_fields(Document) if f.metadata.get(fm.OUTPUT))

    @staticmethod
    def fields_choices() -> tuple:
        return Document.available_fields_names()


class Librarian:

    def __init__(self, db=c.DB_FILE, table=c.TABLE_NAME, debug=False):
        self.conn = sqlite3.connect(db)
        self.table = table
        if debug:
            self.conn.set_trace_callback(print)

    @staticmethod
    def _stringify_fields(fields):
        return ', '.join(fields)

    def create_fts5_table(self):
        self.conn.load_extension(c.SNOWBALL_SO)
        fields = self._stringify_fields(Document.fields_names())
        self.conn.execute(f"""CREATE VIRTUAL TABLE IF NOT EXISTS {self.table} 
                              USING FTS5({fields}, tokenize='snowball {c.STEM_LANGUAGE}');""")

    def index(self, target, extensions=c.FILE_EXTENSIONS):  # TODO itertools chunked

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
                d = Document(name=p.as_posix(), content=content, extension=p.suffix, sizee=stats.st_size,
                             created=stats.st_ctime, modified=stats.st_mtime)
                yield astuple(d)

        with self.conn:
            placeholder = '(' + ','.join('?' for _ in range(len(get_fields(Document)))) + ')'
            self.conn.executemany(f"INSERT INTO {self.table} VALUES {placeholder};", list(_documents_iter()))

    def match(self, query, fields: tuple = Document.available_fields_names(), limit=c.RESULTS_LIMIT):
        cur = self.conn.cursor()
        snippet_string = f"snippet({self.table}, -1, '', '', '', {c.MAX_TOKENS})"
        fields = self._stringify_fields(fields)
        cur.execute(f"""SELECT {fields}, {snippet_string} 
                    FROM {self.table} 
                    WHERE {self.table}  
                    MATCH '{query}'
                    LIMIT {limit};""")
        return cur.fetchall()


def fields_type(arg) -> tuple:
    args = arg.strip().split(',')
    fields = Document.available_fields_names()
    valid_fields = set(args) & set(fields)
    if not valid_fields:
        raise ArgumentTypeError('Has to be contain at least one valid name.')

    ordered = filter(lambda f: f in valid_fields, args)
    return tuple(ordered)


if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ADHFormatter)
    subparsers = parser.add_subparsers(title='available commands', description='Use -h with each of them to get help.',
                                       dest='command', required=True)
    index_parser = subparsers.add_parser('index', formatter_class=ADHFormatter,
                                         help='Command to build a db and index. Have to be run once.')
    match_parser = subparsers.add_parser('match', formatter_class=ADHFormatter,
                                          help='Command to run query on indexed files.')

    parser.add_argument('--db', default=c.DB_FILE, help='DB file path.')
    parser.add_argument('--table', default=c.TABLE_NAME, help='Table name to store files content.')
    parser.add_argument('--debug', action='store_true', help='Print additional events and sqlite statements.')

    index_parser.add_argument('target', help='Directory to build an index on.')
    index_parser.add_argument('--file-extensions', type=frozenset, default=c.FILE_EXTENSIONS,
                              metavar='string', help='List of file extensions separated by space which to scan only.')
    index_parser.add_argument('--language', default=c.STEM_LANGUAGE)  # TODO

    match_parser.add_argument('query', help='Sqlite query term executed by "MATCH" statement. '
                                            'Syntax can be found on https://sqlite.org/fts5.html#full_text_query_syntax.')
    match_parser.add_argument('--limit', default=c.RESULTS_LIMIT, help='Max count of results.')
    match_parser.add_argument('--fields', dest='fields', metavar='field,...', type=fields_type,
                              default=Config.default_fields(),
                              help=f'List of document fields to retrieve separated by comma, order is preserved. '
                                   f'Choices: {Config.fields_choices()}.')
    match_parser.add_argument('--format', dest='output_format', default=c.RAW_FORMAT,
                              choices=(c.RAW_FORMAT, c.MD_FORMAT, c.CSV_FORMAT),
                              help='Chose a results output format.')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()

    lbn = Librarian(db=args.db, table=args.table, debug=args.debug)
    lbn.create_fts5_table()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format='%(message)s')

    if args.command == 'index':
        lbn.index(args.target, extensions=args.file_extensions)
    elif args.command == 'match':
        documents = lbn.match(args.query, fields=args.fields, limit=args.limit)
        logging.info(documents)