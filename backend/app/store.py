"""The in-memory store. Seed data arrives with issue 002."""


class Store:
    """Holds all application data. It holds no data yet."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Return the store to its initial state, dropping anything added since."""
        self.__dict__.clear()
        # Later issues initialise their collections here.


store = Store()


def get_store() -> Store:
    """FastAPI dependency that returns the module-level store."""
    return store
