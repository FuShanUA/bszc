# Bid-Collusion Checking Design Spec

## 1. Goal
Reverse-engineer bid-collusion software inspection rules to pre-check bid files. Compare primary bid PDF with secondary bid PDFs to detect overlaps in metadata, image assets, and text content.

## 2. Detection Logic
*   **Metadata Checks**: Compare creation time, modification time, creator tool, and font lists.
*   **Asset Checks**: Extract and compare MD5 hashes of embedded images to detect shared assets.
*   **Text Checks**: Page-by-page text extraction, whitespace/noise removal, character-level sliding window N-gram similarity (e.g., N=15), and Jaccard similarity score.

## 3. Output Schema
*   Secondary Bidder Name
*   Primary Page Number(s)
*   Secondary Page Number(s)
*   Similarity Rate (0-1.0)
*   Collusion Description / Snippet matched

## 4. Technical Stack
*   Python 3.x
*   Virtual Environment (`.venv`)
*   `pypdf` for text/metadata/image extraction
*   Standard library for N-gram matching
