import os
import chromadb
from sentence_transformers import SentenceTransformer

# Load embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Chroma persistent storage
client = chromadb.PersistentClient(path="./vector_db")

try:
    client.delete_collection(name="sar_knowledge")
    print("Cleared existing collection.")
except Exception:
    pass

collection = client.get_or_create_collection(name="sar_knowledge")

# function to read txt files and tag metadata by source file
def load_documents(data_folder):
    documents = []
    metadatas = []

    for file in os.listdir(data_folder):
        if file.endswith(".txt"):
            path = os.path.join(data_folder, file)

            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

                chunks = text.split("\n---\n")

                for chunk in chunks:
                    chunk = chunk.strip()
                    if chunk:
                        documents.append(chunk)

                        # auto-detect document type for metadata filtering
                        if "TYPOLOGY" in chunk:
                            doc_type = "typology"
                        elif "GUIDELINE" in chunk:
                            doc_type = "guideline"
                        elif "TEMPLATE" in chunk:
                            doc_type = "template"
                        elif "EXAMPLE SAR" in chunk:
                            doc_type = "example"
                        else:
                            doc_type = "general"

                        metadatas.append({"type": doc_type, "source": file})

    return documents, metadatas


# load txt documents
docs, metadatas = load_documents("../data")
print(f"Loaded {len(docs)} document chunks")

# create embeddings
embeddings = model.encode(docs).tolist()

# store in chroma with metadata
ids = [f"doc_{i}" for i in range(len(docs))]

collection.add(
    documents=docs,
    embeddings=embeddings,
    ids=ids,
    metadatas=metadatas
)

print("Documents successfully stored in ChromaDB")