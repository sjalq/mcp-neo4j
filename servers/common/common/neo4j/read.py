import logging
from typing import Any, Optional

from neo4j import AsyncDriver, AsyncTransaction


async def _read(
    tx: AsyncTransaction, query: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    A unit of work to be executed in a read transaction.

    Parameters
    ----------
    tx: AsyncTransaction
        The transaction object to execute with.
    query: str
        The query to execute.
    params: dict[str, Any]
        The parameters to pass to the query.

    Returns
    -------
    list[dict[str, Any]]
        A list of dictionaries containing the results of the query.
    """

    raw_results = await tx.run(query, params)
    eager_results = await raw_results.to_eager_result()

    return [r.data() for r in eager_results.records]


async def execute_read_query(
    neo4j_driver: AsyncDriver,
    query: str,
    params: dict[str, Any] = dict(),
    database: str = "neo4j",
    logger: Optional[logging.Logger] = None,
    raise_on_error: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute a read query on the Neo4j database.

    Parameters
    ----------
    neo4j_driver: AsyncDriver
        The Neo4j driver to use.
    query: str
        The query to execute.
    params: dict[str, Any], optional
        The parameters to pass to the query, by default dict().
    database: str, optional
        The database to use, by default "neo4j".
    logger: Optional[logging.Logger], optional
        The logger to use, by default None.
    raise_on_error: bool, optional
        Whether to raise an exception on error. If false, will return a list of dictionaries with the error message(s). By default False.

    Returns
    -------
    list[dict[str, Any]]
        A list of dictionaries containing the results of the query or error messages.
    """
    try:
        async with neo4j_driver.session(database=database) as session:
            results = await session.execute_read(_read, query, params)

            if logger:
                logger.debug(f"Read query returned {len(results)} rows")

            return results

    except Exception as e:
        logger.error(f"Database error executing read query: {e}")
        if raise_on_error:
            raise e
        return [
            {"error": str(e), "query": query, "params": params, "database": database}
        ]
