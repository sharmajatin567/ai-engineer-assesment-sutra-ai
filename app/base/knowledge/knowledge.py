from abc import ABC, abstractmethod

from app.utils import chunk_id

# Base class for vector store operations
class KnowledgeBase(ABC):

    def __init__(self):
        pass

    @abstractmethod
    async def search(self, query, filter):
        pass

    @abstractmethod
    async def bulk_insert(self, documents, metadata):
        pass

# ChromaDB is used as vector store - local AsyncHTTPClient for async operations
class ChromaDBKnowledgeBase(KnowledgeBase):

    def __init__(self, config):
        import chromadb

        # Section based collection for indexing section chunks
        self.section_index_name = config.get('SECTION_INDEX_NAME')
        if not self.section_index_name:
            raise ValueError("SECTION_INDEX_NAME not present in config")
        
        # Chunk based collection with overlap for factual lookup
        self.chunk_index_name = config.get('CHUNK_INDEX_NAME')
        if not self.chunk_index_name:
            raise ValueError("CHUNK_INDEX_NAME not present in config")
        

        self.top_k = config.get('TOP_K', 5)
        self.similarity_threshold = config.get('SIMILARITY_THRESHOLD', 0.0)
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 8000)
        self._chromadb = chromadb
        self._client = None

    async def _collection(self, collection_name):
        """Function to initialize collection for operations. Creates new collection if collection does not exist"""

        if self._client is None:
            self._client = await self._chromadb.AsyncHttpClient(host=self.host, port=self.port)

        return await self._client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )

    async def search(self, query, collection_name, top_k=None, filter=None):
        "Performs similarity search with metadata filtering"
        collection = await self._collection(collection_name)


        result = await collection.query(
            query_texts=[query],
            n_results=top_k or self.top_k,
            where=filter or None,
        )
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        matches = []

        for document, metadata, distance in zip(documents, metadatas, distances):
            similarity = 1 - distance
            if similarity >= self.similarity_threshold:
                matches.append({
                    "document": document,
                    "metadata": metadata,
                    "similarity": round(similarity, 3),
                })
        return matches

    async def bulk_insert(self, documents, metadata, collection_name):
        """Inserts documents and metadatas in bulk to the collection"""
        collection = await self._collection(collection_name)

        # ChromaDB required IDs to embed documents
        ids = [chunk_id(collection_name, f"{index}:{document}")
               for index, document in enumerate(documents)]
        await collection.upsert(documents=documents, metadatas=metadata, ids=ids)
        return len(documents)


class KnowledgeBankClientFactory():

    def __init__(self, config):

        # Class map for vector store providers
        self.client_map = {
            "chromadb": ChromaDBKnowledgeBase
        }

        knowledge_config = config.get("KNOWLEDGE_CONFIG", {})
        default_provider = knowledge_config.get("DEFAULT_PROVIDER")

        provider_class = self.client_map.get(default_provider)
        if not provider_class:
            raise ValueError("DEFAULT_PROVIDER not present in config")
        
        provider_config = knowledge_config.get("PROVIDERS", {}).get(default_provider)
        self.client = provider_class(provider_config)
