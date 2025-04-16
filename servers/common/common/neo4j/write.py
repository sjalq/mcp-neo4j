import logging
from typing import Any, Optional

from neo4j import AsyncDriver, AsyncTransaction


async def _write(
    tx: AsyncTransaction, query: str, params: dict[str, Any]
) -> dict[str, Any]:
    """
    A unit of work to be executed in a write transaction.

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
    dict[str, Any]
        A dictionary containing the summary results of the query.
    """

    results = await tx.run(query, params)
    return results


async def execute_write_query(
    neo4j_driver: AsyncDriver,
    query: str,
    params: dict[str, Any] = dict(),
    database: str = "neo4j",
    logger: Optional[logging.Logger] = None,
    raise_on_error: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute a write query on the Neo4j database.

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
            raw_results = await session.execute_write(_write, query, params)

            results = raw_results._summary.counters.__dict__

            if logger:
                logger.debug(f"Write query summary: {results}")

            return results

    except Exception as e:
        logger.error(f"Database error executing write query: {e}")
        if raise_on_error:
            raise e
        return [
            {"error": str(e), "query": query, "params": params, "database": database}
        ]
