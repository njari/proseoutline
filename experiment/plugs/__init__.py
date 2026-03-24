# Side-effect imports — each module registers itself via @plug at import time.
from experiment.plugs import chunk_markdown, chunk_recursive, embed_chroma

_ = chunk_markdown, chunk_recursive, embed_chroma
