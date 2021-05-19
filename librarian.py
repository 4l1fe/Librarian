#!venv/bin/python
import sqlite3
import logging

from dataclasses import dataclass, fields as get_fields, astuple
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter as ADHFormatter
from pathlib import Path


class Config:
    DB_FILE = 'fts.db'
    TABLE_NAME = 'documents'
    FILE_EXTENSIONS = frozenset(('.md', ))
    RESULTS_LIMIT = 5


class Constants:
    EXCLUDED = 'venv'
    RAW_FORMAT = 'raw'
    MD_FORMAT = 'md'
    CSV_FORMAT = 'csv'
    SNOWBALL_SO = './fts5stemmer.so'
    STEM_LANGUAGE = 'russian'
    MAX_TOKENS = 10


@dataclass(order=True)
class Document:
    name: str
    content: str
    extension: str
    size: str
    created: str
    modified: str

    @staticmethod
    def fields_names():
        fields = get_fields(Document)
        return ', '.join(f'`{f.name}`' for f in fields)


def lprint(*args, **kwargs):
    logging.debug(*args, **kwargs)


class Librarian:

    def __init__(self, db=Config.DB_FILE, table=Config.TABLE_NAME, debug=False):
        self.conn = sqlite3.connect(db)
        self.table = table
        if debug:
            self.conn.set_trace_callback(print)
            # pass

    def create_fts5_table(self):
        self.conn.load_extension(Constants.SNOWBALL_SO)
        self.conn.execute(f"""CREATE VIRTUAL TABLE IF NOT EXISTS {self.table} 
                              USING FTS5({Document.fields_names()}, tokenize='snowball {Constants.STEM_LANGUAGE}');""")

    def index(self, target, extensions=Config.FILE_EXTENSIONS):  # TODO itertools chunked
        def _documents_iter():
            for p in Path(target).rglob('*'):
                if Constants.EXCLUDED in p.as_posix():
                    logging.debug('Excluded: %s', p.as_posix())
                    continue

                if p.suffix not in extensions:
                    logging.debug('Excluded: %s', p.as_posix())
                    continue

                logging.debug('Indexed: %s', p.as_posix())
                content = p.read_text()
                stats = p.stat()
                name = p.as_posix().rsplit('.', 1)[0]
                d = Document(name=name, content=content, extension=p.suffix, sizee=stats.st_size,
                             created=stats.st_ctime, modified=stats.st_mtime)
                yield astuple(d)

        with self.conn:
            placeholder = '(' + ','.join('?' for _ in range(len(get_fields(Document)))) + ')'
            self.conn.executemany(f"INSERT INTO {self.table} VALUES {placeholder};", list(_documents_iter()))

    def match(self, query, limit=Config.RESULTS_LIMIT):
        cur = self.conn.cursor()
        sql = f"""SELECT name, snippet({self.table}, -1, '', '', '', {Constants.MAX_TOKENS}) 
                        FROM {self.table} 
                        WHERE {self.table}  
                        MATCH '{query}'
                        LIMIT {limit};"""
        logging.debug(sql)
        cur.execute(sql)
        return cur.fetchall()


if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ADHFormatter)
    subparsers = parser.add_subparsers(title='available commands', description='Use -h with each of them to get help.',
                                       dest='command', required=True)
    index_parser = subparsers.add_parser('index', formatter_class=ADHFormatter,
                                         help='Command to build a db and index. Have to be run once.')
    match_parser = subparsers.add_parser('match', formatter_class=ADHFormatter,
                                          help='Command to run query on indexed files.')

    parser.add_argument('--db', default=Config.DB_FILE, help='DB file path.')
    parser.add_argument('--table', default=Config.TABLE_NAME, help='Table name to store files content.')
    parser.add_argument('--debug', action='store_true', help='Print additional events and sqlite statements.')

    index_parser.add_argument('target', help='Directory to build an index on.')
    index_parser.add_argument('--file-extensions', type=frozenset, default=Config.FILE_EXTENSIONS,
                              metavar='string', help='List of file extensions separated by space which to scan only.')

    match_parser.add_argument('query', help='Sqlite query term executed by "MATCH" statement. '
                                            'Syntax can be found on https://sqlite.org/fts5.html#full_text_query_syntax.')
    match_parser.add_argument('--limit', default=Config.RESULTS_LIMIT, help='Max count of results.')
    match_parser.add_argument('--format', dest='output_format', default=Constants.RAW_FORMAT,
                               help='Chose a results output format.',
                              choices=(Constants.RAW_FORMAT, Constants.MD_FORMAT, Constants.CSV_FORMAT))

    args = parser.parse_args()
    if not args.command:
        parser.print_help()

    lbn = Librarian(db=args.db, table=args.table, debug=args.debug)
    lbn.create_fts5_table()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    if args.command == 'index':
        lbn.index(args.target, extensions=args.file_extensions)
    elif args.command == 'match':
        documents = lbn.match(args.query, limit=args.limit)
        logging.info(documents)