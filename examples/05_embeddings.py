"""Embeddings, reranking, and moderation.

Run: python examples/05_embeddings.py
"""
import os

from jarvisclaw import EmbeddingsClient

emb = EmbeddingsClient(api_key=os.environ["JARVISCLAW_API_KEY"])

# --- A single embedding -----------------------------------------------------
# embed() is the convenience path: text in, vector out.
vec = emb.embed("text-embedding-3-small", "Agents settle payments over x402.")
print(f"Dimensions: {len(vec)}")
print(f"First few:  {[round(x, 4) for x in vec[:5]]}")

# --- Several at once --------------------------------------------------------
# One request, one vector per input, order preserved.
vecs = emb.embed_batch("text-embedding-3-small", [
    "USDC on Base",
    "USDC on Solana",
    "A recipe for sourdough",
])
print(f"\n{len(vecs)} vectors of {len(vecs[0])} dimensions each")

# Cosine similarity, to show the first two are closer to each other than to the
# third.
def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb)

print(f"  base vs solana:   {cosine(vecs[0], vecs[1]):.4f}")
print(f"  base vs sourdough:{cosine(vecs[0], vecs[2]):.4f}")

# --- Full response, when you need usage or the model name -------------------
resp = emb.create("text-embedding-3-small", "Settlement finality")
print(f"\nModel: {resp['model']}  usage: {resp.get('usage')}")

# --- Reranking and moderation ----------------------------------------------
#
# Both endpoints exist, but this deployment currently has no rerank or
# moderation model configured, so they answer 503 ("no available channel").
# Check /v1/models for what your gateway actually serves before relying on them.
#
# ranked = emb.rerank_texts(
#     "<a rerank model your gateway serves>",
#     "How do I pay an API with a crypto wallet?",
#     [
#         "Sourdough needs a starter and patience.",
#         "x402 lets a client settle each HTTP request in USDC.",
#         "Rate limits are enforced per API key.",
#     ],
# )
# for r in ranked:                       # [{index, relevance_score}, ...]
#     print(r)
#
# mod = emb.moderate("I would like to learn about cryptography.")
