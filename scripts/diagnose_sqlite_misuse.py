"""Exercise the historical CPython SQLite cursor race outside the SDK test suite.

Both observed and unobserved outcomes are diagnostic, not SDK pass/fail results.
"""

import argparse
import asyncio
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor


def setup_db():
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.executescript(
        'create table test1 (id text primary key not null, val text);\n'
        'create table test2 (id text primary key not null, val text);\n' +
        '\n'.join(f'insert into test1 values ({value}, NULL);' for value in range(1000))
    )
    return db


async def diagnose(max_attempts, timeout, fetchall):
    loop = asyncio.get_running_loop()
    attempts = 0
    print(f'Python {sys.version.split()[0]}, SQLite {sqlite3.sqlite_version}, fetchall={fetchall}')
    with ThreadPoolExecutor(max_workers=1) as executor:
        db = await loop.run_in_executor(executor, setup_db)

        if fetchall:
            def execute(sql, params):
                return db.executemany(sql, params).fetchall()
        else:
            execute = db.executemany

        async def exercise():
            nonlocal attempts
            while attempts < max_attempts:
                # Retain the futures as in the original reproducer. Without
                # fetchall, their cursors can be released on the event-loop thread.
                f1 = loop.run_in_executor(
                    executor, execute, "update test1 set val='derp' where id=?",
                    ((str(i),) for i in range(2))
                )
                f2 = loop.run_in_executor(
                    executor, execute, "update test2 set val='derp' where id=?",
                    ((str(i),) for i in range(2))
                )
                attempts += 1
                await asyncio.gather(f1, f2)

        try:
            await asyncio.wait_for(exercise(), timeout)
        except sqlite3.InterfaceError as error:
            if str(error) != 'Error binding parameter 0 - probably unsupported type.':
                raise
            print(f'Observed the historical binding error after {attempts} attempts: {error}')
        except asyncio.TimeoutError:
            print(f'Not observed within {timeout:g} seconds ({attempts} attempts); result is inconclusive.')
        else:
            print(f'Not observed within {attempts} attempts; result is inconclusive.')
        finally:
            await loop.run_in_executor(executor, db.close)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempts', type=int, default=120000)
    parser.add_argument('--timeout', type=float, default=120,
                        help='time limit in seconds (default: 120)')
    parser.add_argument('--fetchall', action='store_true',
                        help='drain cursors on the worker, as the SDK does')
    args = parser.parse_args()
    if args.attempts <= 0 or args.timeout <= 0:
        parser.error('--attempts and --timeout must be positive')
    # Match the debug event loop used by the original AsyncioTestCase.
    asyncio.run(diagnose(args.attempts, args.timeout, args.fetchall), debug=True)


if __name__ == '__main__':
    main()
