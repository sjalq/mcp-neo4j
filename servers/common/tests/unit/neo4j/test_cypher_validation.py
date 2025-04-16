from common.neo4j.cypher_validation import is_write_query


def test_is_write_query():
    assert is_write_query("CREATE (n:Person {name: 'John'})")
    assert is_write_query("MERGE (n:Person {name: 'John'})")
    assert not is_write_query("MATCH (n:Person {name: 'John'}) RETURN n")