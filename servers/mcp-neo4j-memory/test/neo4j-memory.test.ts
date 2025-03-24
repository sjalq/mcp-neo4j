import { Neo4jMemory } from '../src/neo4j-memory';
import { KnowledgeGraph, Entity, Relation } from "@neo4j/graphrag-memory";

// Mock Neo4j driver
const mockExecuteQuery = jest.fn();
const mockNeo4jDriver = {
  executeQuery: mockExecuteQuery
};

describe('Neo4jMemory', () => {
  let memory: Neo4jMemory;

  beforeEach(() => {
    memory = new Neo4jMemory(mockNeo4jDriver as any);
    mockExecuteQuery.mockClear();
  });

  describe('createEntities', () => {
    it('should create entities successfully', async () => {
      const entities: Entity[] = [
        { name: 'entity1', entityType: 'type1', observations: ['obs1'] },
        { name: 'entity2', entityType: 'type2', observations: ['obs2'] }
      ];

      mockExecuteQuery.mockResolvedValueOnce({ records: [] });

      const result = await memory.createEntities(entities);

      expect(mockExecuteQuery).toHaveBeenCalledWith(
        expect.stringContaining('UNWIND $entities as entity'),
        { entities }
      );
      expect(result).toEqual(entities);
    });
  });

  describe('createRelations', () => {
    it('should create relations successfully', async () => {
      const relations: Relation[] = [
        { from: 'entity1', to: 'entity2', relationType: 'RELATES_TO' }
      ];

      mockExecuteQuery.mockResolvedValueOnce({ records: [] });

      const result = await memory.createRelations(relations);

      expect(mockExecuteQuery).toHaveBeenCalledWith(
        expect.stringContaining('UNWIND $relations as relation'),
        { relations }
      );
      expect(result).toEqual(relations);
    });
  });

  describe('addObservations', () => {
    it('should add observations successfully', async () => {
      const observations = [
        { entityName: 'entity1', contents: ['new_obs1'] }
      ];

      mockExecuteQuery.mockResolvedValueOnce({
        records: [{ get: (key: string) => key === 'name' ? 'entity1' : ['new_obs1'] }]
      });

      const result = await memory.addObservations(observations);

      expect(mockExecuteQuery).toHaveBeenCalledWith(
        expect.stringContaining('UNWIND $observations as obs'),
        { observations }
      );
      expect(result).toEqual([
        { entityName: 'entity1', addedObservations: ['new_obs1'] }
      ]);
    });
  });

  describe('deleteEntities', () => {
    it('should delete entities successfully', async () => {
      const entityNames = ['entity1', 'entity2'];

      mockExecuteQuery.mockResolvedValueOnce({ records: [] });

      await memory.deleteEntities(entityNames);

      expect(mockExecuteQuery).toHaveBeenCalledWith(
        expect.stringContaining('UNWIND $entities as name'),
        { entities: entityNames }
      );
    });
  });

  describe('searchNodes', () => {
    it('should search nodes successfully', async () => {
      const query = 'test';
      const mockGraph: KnowledgeGraph = {
        entities: [{ name: 'entity1', entityType: 'type1', observations: [] }],
        relations: []
      };

      mockExecuteQuery.mockResolvedValueOnce({
        records: [{
          get: (key: string) => {
            if (key === 'nodes') return [{ get: (k: string) => k === 'name' ? 'entity1' : k === 'entityType' ? 'type1' : [] }];
            return [];
          }
        }]
      });

      const result = await memory.searchNodes(query);

      expect(mockExecuteQuery).toHaveBeenCalledWith(
        expect.stringContaining('CALL db.index.fulltext.queryNodes'),
        expect.any(Object)
      );
      expect(result.entities).toHaveLength(1);
    });
  });

  describe('openNodes', () => {
    it('should open nodes successfully', async () => {
      const names = ['entity1'];
      const mockGraph: KnowledgeGraph = {
        entities: [{ name: 'entity1', entityType: 'type1', observations: [] }],
        relations: []
      };

      mockExecuteQuery.mockResolvedValueOnce({
        records: [{
          get: (key: string) => {
            if (key === 'nodes') return [{ get: (k: string) => k === 'name' ? 'entity1' : k === 'entityType' ? 'type1' : [] }];
            return [];
          }
        }]
      });

      const result = await memory.openNodes(names);

      expect(mockExecuteQuery).toHaveBeenCalledWith(
        expect.stringContaining('CALL db.index.fulltext.queryNodes'),
        expect.any(Object)
      );
      expect(result.entities).toHaveLength(1);
    });
  });
});