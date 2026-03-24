from experiment import Experiment, Plug
from settings import vault_dir


class IngestAndChunk(Experiment):
    id         = "ingest-and-chunk-v1"
    input_path = vault_dir()
    plugs = [
        Plug("chunk_recursive", order=0, config={"chunk_size": 200, "chunk_overlap": 20}),
    ]
