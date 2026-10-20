"""Hybrid merge of ranked retrieval lists with Reciprocal Rank Fusion (F3, coach mode: Ethan implements)."""

DEFAULT_RRF_K = 60
DEFAULT_TOP_N = 10


def merge_ranked_lists(ranked_lists, k=DEFAULT_RRF_K, top_n=DEFAULT_TOP_N):
    merged = {}

    for ranked_list in ranked_lists:
        for hit in ranked_list:
            chunk_id = hit["chunk_id"]

            if chunk_id not in merged:
                merged[chunk_id] = {
                    "fused_score": 0.0,
                    "sources": []
                }
                # Copy shared details from the first hit
                for key, value in hit.items():
                    if key != "rank" and key != "score" and key != "source":
                        merged[chunk_id][key] = value

            merged[chunk_id]["fused_score"] += 1 / (k + hit["rank"])
            merged[chunk_id]["sources"].append({
                "source": hit["source"],
                "kb_id": hit["kb_id"],
                "rank": hit["rank"],
                "score": hit["score"]
            })

    
    results = list(merged.values())
    results = sorted(results, key=lambda x: (-x["fused_score"], x["chunk_id"]))
    
    return results[:top_n]