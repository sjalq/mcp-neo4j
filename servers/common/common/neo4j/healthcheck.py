import asyncio
import sys
import time

from neo4j import AsyncDriver, Driver
from neo4j.exceptions import DatabaseError


async def attempt_neo4j_connection_async(
    neo4j_driver: AsyncDriver,
    database: str,
    initial_delay: float = 3.0,
    max_attempts: int = 3,
    retry_delay_multiplier: float = 2.0,
):
    """Async function used to check the Neo4j database connection."""
    attempts = 0
    success = False
    last_exception = DatabaseError()

    # Initial delay
    time.sleep(initial_delay)
    print("\nWaiting for Neo4j to Start...\n", file=sys.stderr)

    while not success and attempts < max_attempts:
        try:
            async with neo4j_driver.session(database=database) as session:
                result = await session.run("RETURN 1 AS value")
                record = await result.single()
                if record and record["value"] == 1:
                    success = True
                    print("Successfully connected to Neo4j", file=sys.stderr)

        except Exception as e:
            last_exception = e
            attempts += 1
            retry_delay = (1 + attempts) * retry_delay_multiplier

            print(
                f"Failed connection {attempts} | waiting {retry_delay} seconds...",
                file=sys.stderr,
            )
            print(f"Error: {e}", file=sys.stderr)

            time.sleep(retry_delay)

    await neo4j_driver.close()

    if not success:
        raise last_exception


def neo4j_healthcheck_for_mcp_server(
    neo4j_driver: AsyncDriver,
    database: str,
    max_attempts: int = 3,
    initial_delay: float = 3.0,
    retry_delay_multiplier: float = 2.0,
) -> None:
    """
    Confirm that Neo4j is running before continuing.
    Uses the Neo4j async driver but runs in a blocking way to ensure the
    database is available before proceeding.

    Parameters
    ----------
    neo4j_driver: AsyncDriver
        The Neo4j async driver to use.
    database: str
        The name of the Neo4j database.
    max_attempts: int
        Maximum number of connection attempts (default: 3)
    initial_delay: float
        Initial delay in seconds before the first attempt (default: 3.0)
    retry_delay_multiplier: float
        Multiplier for increasing delay between retries (default: 2.0)

    Returns
    -------
    None

    Raises
    ------
    Exception
        If the Neo4j database is not running after the maximum number of attempts.
    """
    print("Confirming Neo4j is running...", file=sys.stderr)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(
            attempt_neo4j_connection_async(
                neo4j_driver,
                database,
                max_attempts,
                initial_delay,
                retry_delay_multiplier,
            )
        )

    except Exception as e:
        print(
            f"Failed to connect to Neo4j after multiple attempts: {e}", file=sys.stderr
        )
        raise

    finally:
        loop.close()
        asyncio.set_event_loop(None)


def neo4j_healthcheck_for_integration_tests(
    neo4j_driver: Driver,
    database: str,
    max_attempts: int = 3,
    initial_delay: float = 3.0,
    retry_delay_multiplier: float = 2.0,
) -> None:
    """
    Confirm that Neo4j is running before continuing.
    Uses the Neo4j async driver but runs in a blocking way to ensure the
    database is available before proceeding.

    Parameters
    ----------
    neo4j_driver: Driver
        The Neo4j driver to use.
    database: str
        The name of the Neo4j database.
    max_attempts: int
        Maximum number of connection attempts (default: 3)
    initial_delay: float
        Initial delay in seconds before the first attempt (default: 3.0)
    retry_delay_multiplier: float
        Multiplier for increasing delay between retries (default: 2.0)

    Returns
    -------
    None

    Raises
    ------
    Exception
        If the Neo4j database is not running after the maximum number of attempts.
    """
    print("Confirming Neo4j is running...", file=sys.stderr)

    attempts = 0
    success = False
    last_exception = DatabaseError()

    # Initial delay
    time.sleep(initial_delay)
    print("\nWaiting for Neo4j to Start...\n", file=sys.stderr)

    while not success and attempts < max_attempts:
        try:
            with neo4j_driver.session(database=database) as session:
                result = session.run("RETURN 1 AS value")
                record = result.single()
                if record and record["value"] == 1:
                    success = True
                    print("Successfully connected to Neo4j", file=sys.stderr)

        except Exception as e:
            last_exception = e
            attempts += 1
            retry_delay = (1 + attempts) * retry_delay_multiplier

            print(
                f"Failed connection {attempts} | waiting {retry_delay} seconds...",
                file=sys.stderr,
            )
            print(f"Error: {e}", file=sys.stderr)

            time.sleep(retry_delay)

    if not success:
        raise last_exception
