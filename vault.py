import os
from pathlib import Path

import networkx as nx
import obsidiantools as otools
from langchain_community.document_loaders import ObsidianLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

import settings
CHROMA_DIR = str(Path(__file__).parent / "chroma_db")


def build_graph():
    vault = otools.api.Vault(Path(settings.vault_dir())).connect().gather()
    return vault.graph


def build_or_load_store():
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    if os.path.exists(CHROMA_DIR):
        return Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    loader = ObsidianLoader(path=settings.vault_dir(), collect_metadata=True)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20, add_start_index=True)
    splits = splitter.split_documents(docs)
    return Chroma.from_documents(splits, embeddings, persist_directory=CHROMA_DIR)


def expand_with_graph(results, store, graph, hops=1):
    expanded = list(results)
    seen_sources = {doc.metadata.get("source", "") for doc in results}
    for doc in results:
        source = doc.metadata.get("source", "")
        note_name = os.path.splitext(os.path.basename(source))[0]
        if note_name not in graph:
            continue
        ego = nx.ego_graph(graph.to_undirected(), note_name, radius=hops)
        neighbors = set(ego.nodes) - {note_name}
        for neighbor in neighbors:
            neighbor_path = os.path.join(settings.vault_dir(), neighbor + ".md")
            if neighbor_path in seen_sources:
                continue
            seen_sources.add(neighbor_path)
            expanded.extend(store.similarity_search(note_name, k=2, filter={"source": neighbor_path}))
    return expanded


def retrieve(store, graph, topic, k=5):
    results = store.similarity_search(topic, k=k)
    return expand_with_graph(results, store, graph)
