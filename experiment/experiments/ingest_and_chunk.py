from experiment import Experiment, Plug
from settings import vault_dir


class IngestAndChunk(Experiment):
    id         = "ingest-and-chunk-v1"
    input_path = vault_dir()
    plugs = [
        Plug("obsidian_ingest", order=0),
        Plug("chunk_recursive",  order=1, config={"chunk_size": 200, "chunk_overlap": 20}),
    ]
