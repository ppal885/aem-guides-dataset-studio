import sys
sys.path.insert(0, 'C:/Users/prashantp/Videos/aem-guides-dataset-studio/backend')
import chromadb
from chromadb.config import DEFAULT_DATABASE, DEFAULT_TENANT

path = 'C:/Users/prashantp/Videos/aem-guides-dataset-studio/backend/storage/chroma_db'
client = chromadb.PersistentClient(path=path, tenant=DEFAULT_TENANT, database=DEFAULT_DATABASE)
for coll in client.list_collections():
    c = client.get_collection(coll.name)
    print(f"  {coll.name}: {c.count()}")
