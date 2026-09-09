from language_tutor.db.migrations import migrate

if __name__ == "__main__":
    migrate()
    print("Schema migration complete.")
