"""Initialize the application's bucket without requiring the retired mc image."""

from app.infrastructure.object_store import ObjectStore


def main() -> None:
    ObjectStore().ensure_bucket_sync()
    print("Application object-storage bucket is ready.")


if __name__ == "__main__":
    main()
