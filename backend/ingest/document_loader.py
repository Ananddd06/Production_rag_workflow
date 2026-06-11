import hashlib
import os
from typing import List, Dict, Optional

class DocumentLoader:
    """Loads and chunks documents into the vector store."""

    def __init__(self, vector_store=None):
        self.vector_store = vector_store
        # Simple chunking params
        self.chunk_size_words = 300
        self.chunk_overlap_words = 50

    def load_text(self, text: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """Split text into chunks and return a list of document dicts."""
        if not text.strip():
            return []
            
        metadata = metadata or {}
        chunks = self._chunk_text(text)
        
        documents = []
        for i, chunk in enumerate(chunks):
            # Create a deterministic ID based on content
            chunk_hash = hashlib.sha256(chunk.encode('utf-8')).hexdigest()[:16]
            doc_id = f"{metadata.get('filename', 'doc')}_{chunk_hash}_{i}"
            
            # Merge chunk info into metadata
            chunk_meta = dict(metadata)
            chunk_meta["chunk_index"] = i
            
            documents.append({
                "id": doc_id,
                "text": chunk,
                "metadata": chunk_meta
            })
            
        return documents

    def load_file(self, filepath: str) -> List[Dict]:
        """Read a .txt or .md file and return chunked documents."""
        if not os.path.exists(filepath):
            return []
            
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.pdf':
            import pypdf
            content = ""
            with open(filepath, 'rb') as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        content += text + "\n"
        else:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        filename = os.path.basename(filepath)
        metadata = {
            "source": filename,
            "filepath": filepath,
            "filename": filename
        }
        return self.load_text(content, metadata)

    def load_directory(self, dirpath: str) -> List[Dict]:
        """Load all .txt and .md files in a directory."""
        if not os.path.isdir(dirpath):
            return []
            
        all_documents = []
        for root, _, files in os.walk(dirpath):
            for file in files:
                if file.lower().endswith(('.txt', '.md', '.pdf')):
                    filepath = os.path.join(root, file)
                    docs = self.load_file(filepath)
                    all_documents.extend(docs)
                    
        return all_documents

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap."""
        words = text.split()
        if not words:
            return []
            
        chunks = []
        i = 0
        while i < len(words):
            chunk_words = words[i:i + self.chunk_size_words]
            chunk_text = " ".join(chunk_words)
            chunks.append(chunk_text)
            
            i += (self.chunk_size_words - self.chunk_overlap_words)
            
            # Avoid getting stuck if overlap is weirdly configured
            if self.chunk_size_words <= self.chunk_overlap_words:
                i += self.chunk_size_words
                
        return chunks
