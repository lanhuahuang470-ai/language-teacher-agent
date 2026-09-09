from language_tutor.retrieval.error_store import ensure_index_jobs, retry_pending

if __name__ == "__main__":
    print(f"Added jobs: {ensure_index_jobs()}; indexed: {retry_pending()}")
