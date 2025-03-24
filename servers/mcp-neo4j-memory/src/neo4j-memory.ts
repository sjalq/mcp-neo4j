import neo4j, { driver, Driver as Neo4jDriver } from 'neo4j-driver';
import { KnowledgeGraphMemory, Entity, KnowledgeGraph, Relation } from "@neo4j/graphrag-memory";
// TODO also store timestamp when memories are created/udpated so that it can be used for decay/archiving
// perhaps also creator/user
// ranking / scoring
export class Neo4jMemory implements KnowledgeGraphMemory {
  constructor(private neo4jDriver: Neo4jDriver) { }

  private async loadGraph(filter:String[] = ["*"]): Promise<KnowledgeGraph> {
      const res = await this.neo4jDriver.executeQuery(
        `
          CALL db.index.fulltext.queryNodes('search', $filter) yield node as entity, score
          MATCH (entity:Memory) WHERE $filter is null OR entity.entityId contains $filter
          OPTIONAL MATCH (entity)-[r]->(other)
          RETURN collect(distinct entity { name: entityId, entityType:type, .observations}) as nodes,
          , collect(r {from: startNode(r).entityId, to:endNode(r).entityId, relationType:type(r)}) as relations
        `, {filter:filter.join(" ")});
      const [kgMemory] = res.records.map(record => {
        const nodes = record.get('nodes') as Array<Map<string, any>>;
        const rels = record.get('relations') as Array<Map<string, any>>;

        return {
          entities: nodes.map(node => ({
            name: node.get('name'),
            entityType: node.get('entityType'),
            observations: node.get('observations')
          }) as Entity),
          relations: rels.map(rel => ({
            from: rel.get('from'),
            to: rel.get('to'),
            relationType: rel.get('relationType')
          }) as Relation)
        } as KnowledgeGraph;
      });
      console.error(JSON.stringify(kgMemory.entities))
      console.error(JSON.stringify(kgMemory.relations))

      return kgMemory;
  }

  private async saveGraph(graph: KnowledgeGraph): Promise<void> {
    await this.createEntities(graph.entities);
    await this.createRelations(graph.relations);
  }

  async createEntities(entities: Entity[]): Promise<Entity[]> {
    await this.neo4jDriver.executeQuery(
      `
      UNWIND $entities as entity
      CALL (entity) {
        MERGE (e:Memory { entityId: entity.name })
        SET e += entity {.type, .observations}
        SET e:$(entity.type)
      } IN TRANSACTIONS OF 10000 ROWS
      `,
      { entities }
    );
    return entities;
  }

  async createRelations(relations: Relation[]): Promise<Relation[]> {
    await this.neo4jDriver.executeQuery(
      `
      UNWIND $relations as relation
      CALL (relation) {
        MATCH (from:Memory),(to:Memory)
        WHERE from.entityId = relation.from
          AND  to.entityId = relation.to
        MERGE (from)-[r:$(relation.relationType)]->(to)
      } IN TRANSACTIONS OF 10000 ROWS
      `,
      { relations }
    );
    return relations;
  }

  async addObservations(observations: { entityName: string; contents: string[] }[]): Promise<{ entityName: string; addedObservations: string[] }[]> {
    const res = await this.neo4jDriver.executeQuery(
      `
      UNWIND $observations as obs  
      CALL (obs) {
        MATCH (e:Memory { entityId: obs.entityName })
        WITH e, [o in obs.contents WHERE o NOT IN e.observations] as new
        SET e.observations = coalesce(e.observations,[]) + new
        RETURN obs.entityName as entityName, new as addedObservations
      } IN TRANSACTIONS OF 10000 ROWS
      RETURN obs.entityName as name, new
      `,
      { observations }
    );
    return res.records.map(r => ({ 
      entityName: r.get('name'), 
      addedObservations: r.get('new') 
    }));
  }

  async deleteEntities(entityNames: string[]): Promise<void> {
    await this.neo4jDriver.executeQuery(
      `
      UNWIND $entities as name
      CALL (name) {
        MATCH (e:Memory { entityId: name })
        DETACH DELETE e
      } IN TRANSACTIONS OF 10000 ROWS
      `,
      { entities: entityNames }
    );
  }

  async deleteObservations(deletions: { entityName: string; observations: string[] }[]): Promise<void> {
    await this.neo4jDriver.executeQuery(
      `
      UNWIND $deletions as d  
      CALL (d) {
        MATCH (e:Memory { entityId: d.entityName })
        SET e.observations = [o in coalesce(e.observations,[]) WHERE o NOT IN d.observations]
      } IN TRANSACTIONS OF 10000 ROWS
      `,
      { deletions }
    );
  }

  async deleteRelations(relations: Relation[]): Promise<void> {
    await this.neo4jDriver.executeQuery(
      `
      UNWIND $relations as relation
      CALL (relation) {
        MATCH (from:Memory),(to:Memory)
        WHERE from.entityId = relation.from
          AND  to.entityId = relation.to
        MATCH (from)-[r:$(relation.relationType)]->(to)
        DELETE r
      } IN TRANSACTIONS OF 10000 ROWS
      `,
      { relations }
    );
  }

  async readGraph(): Promise<KnowledgeGraph> {
    return this.loadGraph();
  }

  // Very basic search function
  async searchNodes(query: string): Promise<KnowledgeGraph> {
    return this.loadGraph([query]); // todo vector search
  }

  async openNodes(names: string[]): Promise<KnowledgeGraph> {
    return this.loadGraph(names);
  }
}
